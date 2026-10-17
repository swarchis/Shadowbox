"""The one door to every model call: Crusoe (OpenAI-compatible) or the offline mock.

Every call is logged to the cost ledger with tokens and cost. The hard spend cap is enforced
against the ledger total, so it survives restarts.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import threading
import time
from dataclasses import dataclass

from . import config, store


class SpendCapExceeded(RuntimeError):
    pass


class FatalLLMError(RuntimeError):
    """A failure no retry can fix (bad key, unknown model, permission). Stops the run instead of
    being recorded as a failed design."""


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    reasoning: str | None = None
    finish_reason: str | None = None


def price_of(model: str) -> tuple[float, float]:
    return config.PRICES.get(model, config.DEFAULT_PRICE)


def cost_of(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = price_of(model)
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_reasoning(text: str) -> tuple[str, str | None]:
    """Remove <think>...</think> blocks some reasoning models put in the content."""
    if not text:
        return "", None
    thoughts = "\n".join(m.group(0) for m in _THINK_RE.finditer(text)) or None
    text = _THINK_RE.sub("", text)
    if "</think>" in text:  # opening tag was in a prefix the server stripped
        thoughts, text = text.split("</think>", 1)
    return text.strip(), thoughts


class Ledger:
    """Spend tracking backed by the ledger file. Thread- and task-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._loaded_from = None
        self.total = 0.0
        self.calls = 0

    def _ensure_loaded(self):
        path = store.ledger_path()
        if self._loaded_from != path:
            rows = store.read_jsonl(path)
            self.total = sum(r.get("cost_usd", 0.0) for r in rows)
            self.calls = len(rows)
            self._loaded_from = path

    def check(self):
        with self._lock:
            self._ensure_loaded()
            if self.total >= config.SPEND_CAP_USD:
                raise SpendCapExceeded(f"spend cap ${config.SPEND_CAP_USD:.2f} reached (spent ${self.total:.2f})")

    def record(self, row: dict):
        with self._lock:
            self._ensure_loaded()
            store.append_jsonl(store.ledger_path(), row)
            self.total += row.get("cost_usd", 0.0)
            self.calls += 1

    def snapshot(self) -> tuple[float, int]:
        with self._lock:
            self._ensure_loaded()
            return self.total, self.calls


LEDGER = Ledger()

_last_heartbeat = [0.0]


def _heartbeat():
    """Refresh state.json's updated_at (and spend) at most every 30 s while calls are flowing, so the UI
    can tell a live run from one that was killed."""
    now = time.monotonic()
    if now - _last_heartbeat[0] < 30:
        return
    _last_heartbeat[0] = now
    try:
        st = store.read_state()
        if st.get("status") == "running":
            spent, calls = LEDGER.snapshot()
            store.update_state(spend_usd=round(spent, 4), llm_calls=calls)
    except Exception:
        pass


class LLMClient:
    """Use `await client.chat(...)`. One instance is shared by every agent in a run."""

    def __init__(self, mock: bool | None = None, concurrency: int | None = None):
        self.mock = config.MOCK if mock is None else mock
        self._concurrency = concurrency or config.LLM_CONCURRENCY
        self._sems: dict[int, asyncio.Semaphore] = {}  # one per event loop (asyncio objects are loop-bound)
        self._client = None
        self._seed_ok: dict[str, bool] = {}  # per model: provider accepts `seed`
        self._extra_ok: dict[str, bool] = {}  # per model: provider accepts chat_template_kwargs
        self._req_times: dict[str, list[float]] = {}  # per model: request start times in the last minute
        if self.mock:
            from .mock_llm import MockProvider

            self._mock = MockProvider()
        else:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=config.CRUSOE_BASE_URL, api_key=config.CRUSOE_API_KEY, timeout=config.LLM_TIMEOUT_S, max_retries=0
            )

    @property
    def sem(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        sem = self._sems.get(id(loop))
        if sem is None:
            sem = self._sems[id(loop)] = asyncio.Semaphore(self._concurrency)
        return sem

    def model_for(self, model_key: str) -> str:
        return config.MODELS.get(model_key, model_key)

    async def chat(
        self,
        *,
        role: str,
        messages: list[dict],
        model_key: str = "worker",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tag: str = "",
        meta: dict | None = None,
        thinking: str | None = None,
    ) -> LLMResponse:
        """role: planner|writer|debugger|attacker|multi_attacker|judge|coach (used for logging and the mock).
        meta: free-form context for logs; the mock also reads it (problem_id, rules, ...).
        thinking: "off" | "low" | "on" overrides the role default (a playbook setting can choose it)."""
        model = self.model_for(model_key)
        max_tokens = max_tokens or config.MAX_TOKENS.get(role, 4096)
        LEDGER.check()
        async with self.sem:
            LEDGER.check()
            t0 = time.monotonic()
            finish = None
            if self.mock:
                text = await self._mock.respond(role=role, messages=messages, temperature=temperature, meta=meta or {})
                tin = sum(len(m.get("content", "")) for m in messages) // 4
                tout = len(text) // 4
                reasoning = None
            else:
                text, reasoning, tin, tout, finish = await self._call_real(model, role, messages, temperature, max_tokens, tag, thinking)
            latency = time.monotonic() - t0
        cost = cost_of(model, tin, tout)
        LEDGER.record(
            {
                "ts": store.now_iso(),
                "role": role,
                "model": model,
                "tag": tag,
                "input_tokens": tin,
                "output_tokens": tout,
                "cost_usd": round(cost, 6),
                "latency_s": round(latency, 2),
                "finish_reason": finish,
                "mock": self.mock,
            }
        )
        _heartbeat()
        return LLMResponse(text, model, tin, tout, cost, latency, reasoning, finish)

    async def _throttle(self, model: str) -> None:
        """Client-side requests-per-minute cap per model (Crusoe's limits are per model)."""
        window = self._req_times.setdefault(model, [])
        while True:
            now = time.monotonic()
            while window and now - window[0] > 60:
                window.pop(0)
            if len(window) < config.RPM_PER_MODEL:
                window.append(now)
                return
            await asyncio.sleep(max(0.05, 60 - (now - window[0])))

    def _thinking(self, model: str, role: str) -> str:
        if "emotron" not in model.lower():
            return "default"
        return config.COACH_THINKING if role == "coach" else config.WORKER_THINKING

    async def _call_real(self, model, role, messages, temperature, max_tokens, tag, thinking_override=None):
        from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, BadRequestError,
                            NotFoundError, PermissionDeniedError, RateLimitError)

        msgs = [dict(m) for m in messages]
        thinking = self._thinking(model, role)
        if thinking_override in ("off", "low", "on") and thinking != "default":
            thinking = thinking_override
        delay = 1.0
        last_err = None
        attempts = 0
        tin_total = tout_total = 0
        truncated = None  # (text, reasoning) of a reply cut off at max_tokens, kept as a fallback
        while attempts <= config.LLM_MAX_RETRIES:
            attempts += 1
            kwargs = dict(model=model, messages=msgs, temperature=temperature, max_tokens=max_tokens)
            # A fixed seed only for deterministic (temperature-0) work: sampled drafts must differ.
            if temperature == 0 and self._seed_ok.get(model, True):
                kwargs["seed"] = config.LLM_SEED
            if thinking in ("on", "off", "low") and self._extra_ok.get(model, True):
                # Nemotron 3 / 3.5 (per Crusoe's skill file): enable_thinking toggles reasoning, low_effort
                # cuts reasoning tokens; force_nonempty_content is recommended for coding agents.
                ctk = {"enable_thinking": thinking != "off", "force_nonempty_content": True}
                if thinking == "low":
                    ctk["low_effort"] = True
                kwargs["extra_body"] = {"chat_template_kwargs": ctk}
            if role == "coach":
                kwargs["timeout"] = config.COACH_TIMEOUT_S
            await self._throttle(model)
            try:
                resp = await self._client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                raw = choice.message.content or ""
                text, thoughts = strip_reasoning(raw)
                reasoning = (getattr(choice.message, "reasoning_content", None) or getattr(choice.message, "reasoning", None)
                             or thoughts)
                usage = resp.usage
                tin_total += getattr(usage, "prompt_tokens", 0) or 0
                tout_total += getattr(usage, "completion_tokens", 0) or 0
                finish = getattr(choice, "finish_reason", None)
                if (finish == "length" and role in config.TRUNCATION_RETRY_ROLES
                        and max_tokens < config.MAX_TOKENS_CEILING and truncated is None):
                    # Cut off (often by long reasoning): retry once with a bigger budget.
                    truncated = (text, reasoning)
                    store.event("llm_truncated", f"{role} reply hit max_tokens={max_tokens}; retrying with {max_tokens * 2}", tag=tag)
                    max_tokens = min(max_tokens * 2, config.MAX_TOKENS_CEILING)
                    continue
                return text, reasoning, tin_total, tout_total, finish
            except BadRequestError as e:
                # Some providers reject optional params; drop them for this model and retry.
                msg = str(e).lower()
                if "seed" in kwargs and "seed" in msg:
                    self._seed_ok[model] = False
                    continue
                if "extra_body" in kwargs and ("chat_template" in msg or "enable_thinking" in msg or "extra" in msg):
                    self._extra_ok[model] = False
                    continue
                if truncated is not None:  # the bigger budget was refused: use the cut-off reply we already have
                    store.event("llm_truncated", f"{role}: larger max_tokens rejected; using the truncated reply", tag=tag)
                    return truncated[0], truncated[1], tin_total, tout_total, "length"
                if "max_tokens" in msg or "context" in msg:
                    raise FatalLLMError(f"{model}: request rejected ({e}). Lower MAX_TOKENS in engine/config.py.") from e
                raise FatalLLMError(f"{model}: request rejected: {e}") from e
            except (AuthenticationError, PermissionDeniedError) as e:
                raise FatalLLMError(f"Crusoe rejected the API key for {model}: {e}") from e
            except NotFoundError as e:
                raise FatalLLMError(f"Model '{model}' not found on Crusoe. Check the model IDs in engine/config.py: {e}") from e
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                last_err = e
            except APIStatusError as e:
                if e.status_code < 500:
                    raise FatalLLMError(f"{model}: HTTP {e.status_code}: {e}") from e
                last_err = e
            if attempts <= config.LLM_MAX_RETRIES:
                store.event("llm_retry", f"{role} call failed ({type(last_err).__name__}); retry {attempts} in {delay:.0f}s", tag=tag)
                await asyncio.sleep(delay + random.uniform(0, 0.5 * delay))  # jitter so parallel retries don't collide
                delay = min(delay * 2, 60)
        raise RuntimeError(f"LLM call failed after {config.LLM_MAX_RETRIES} retries: {last_err}")


# ------------------------------------------------------------------ output parsing helpers
_FENCE_RE = re.compile(r"^[ \t]*```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)^[ \t]*```", re.S | re.M)


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    """All ``` fenced blocks as (language, body), fences matched line by line."""
    return [(lang.lower(), body) for lang, body in _FENCE_RE.findall(text or "")]


def extract_code(text: str, lang: str = "verilog") -> str | None:
    """The design: prefer a fenced block declaring TopModule (last one wins), then any fenced Verilog
    block with a module, then a bare `module TopModule ... endmodule` span starting at a line."""
    blocks = fenced_blocks(text)
    verilog_langs = {"verilog", "systemverilog", "sv", "v", ""}
    cands = [b for l, b in blocks if l in verilog_langs and re.search(r"\bmodule\s+TopModule\b", b)]
    if not cands:
        cands = [b for l, b in blocks if l in verilog_langs and re.search(r"^\s*module\b", b, re.M)]
    if cands:
        return cands[-1].strip() + "\n"
    m = re.search(r"^[ \t]*module\s+TopModule\b.*?\bendmodule\b", text or "", re.S | re.M)
    if not m:
        m = re.search(r"^[ \t]*module\b.*\bendmodule\b", text or "", re.S | re.M)
    return m.group(0).strip() + "\n" if m else None


def extract_json(text: str):
    """Parse the last ```json block, then any other fenced block, then the outermost {...} or [...]
    span of the text with fenced non-JSON blocks removed."""
    blocks = fenced_blocks(text)
    ordered = [b for l, b in reversed(blocks) if l == "json"] + [b for l, b in reversed(blocks) if l != "json"]
    for b in ordered:
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    rest = _FENCE_RE.sub("", text or "")
    for src in (rest, text or ""):
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = src.find(opener), src.rfind(closer)
            if 0 <= start < end:
                try:
                    return json.loads(src[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("no JSON found in model output")
