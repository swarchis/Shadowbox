"""Real-API code path, exercised against a scripted fake of the OpenAI client (no network, no key).

Covers what can't be seen in mock mode: seeds, retries, fatal errors, truncation, parameter fallbacks,
and how API failures flow through the Builder and the result caches.
"""
import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from engine import config, gatekeeper, llm, playbook, store
from engine.builder import build
from engine.coach import parse_proposals
from engine.dataset import load_problems


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "VERSIONS_DIR", tmp_path / "versions")
    monkeypatch.setattr(config, "LEDGER_PATH", None)
    monkeypatch.setattr(config, "CRUSOE_API_KEY", "test-key")
    monkeypatch.setattr(config, "SPEND_CAP_USD", 100.0)
    monkeypatch.setattr(llm, "LEDGER", llm.Ledger())

    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    yield


def _resp(text="ok", finish="stop", tin=10, tout=20):
    msg = SimpleNamespace(content=text, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)],
                           usage=SimpleNamespace(prompt_tokens=tin, completion_tokens=tout))


def _err(cls, status, msg="boom"):
    req = httpx.Request("POST", "https://api.example/v1/chat/completions")
    return cls(msg, response=httpx.Response(status, request=req), body=None)


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0) if self.script else _resp()
        if isinstance(item, Exception):
            raise item
        return item


def client_with(script) -> tuple[llm.LLMClient, FakeCompletions]:
    c = llm.LLMClient(mock=False)
    fake = FakeCompletions(script)
    c._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return c, fake


def chat(c, **kw):
    kw.setdefault("role", "writer")
    kw.setdefault("messages", [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}])
    return asyncio.run(c.chat(**kw))


def test_seed_only_for_temperature_zero():
    c, fake = client_with([_resp(), _resp()])
    chat(c, temperature=0.0)
    chat(c, temperature=0.7)
    assert fake.calls[0]["seed"] == config.LLM_SEED
    assert "seed" not in fake.calls[1]  # sampled drafts must be able to differ


def test_truncated_reply_is_retried_with_bigger_budget():
    c, fake = client_with([_resp("partial", finish="length", tout=100), _resp("full", tout=50)])
    r = chat(c, max_tokens=1000, role="coach")  # only long-form roles get the bigger-budget retry
    assert r.text == "full" and r.output_tokens == 150  # both attempts are billed
    assert fake.calls[1]["max_tokens"] == 2000


@pytest.mark.parametrize("exc", [_err(openai.AuthenticationError, 401), _err(openai.PermissionDeniedError, 403),
                                 _err(openai.NotFoundError, 404)])
def test_unfixable_errors_are_fatal(exc):
    c, fake = client_with([exc])
    with pytest.raises(llm.FatalLLMError):
        chat(c)
    assert len(fake.calls) == 1  # no pointless retries


def test_rate_limit_is_retried_then_succeeds():
    c, fake = client_with([_err(openai.RateLimitError, 429), _err(openai.InternalServerError, 500), _resp("done")])
    assert chat(c).text == "done" and len(fake.calls) == 3


def test_rejected_seed_is_dropped_for_that_model_only():
    c, fake = client_with([_err(openai.BadRequestError, 400, "unsupported parameter: seed"), _resp(), _resp()])
    chat(c, temperature=0.0)
    assert "seed" in fake.calls[0] and "seed" not in fake.calls[1]
    chat(c, temperature=0.0, model_key="coach", role="coach")
    assert "seed" in fake.calls[2]  # a different model keeps its seed


def test_thinking_off_for_nemotron_worker(monkeypatch):
    monkeypatch.setattr(config, "WORKER_THINKING", "off")
    c, fake = client_with([_resp()])
    chat(c)
    call = fake.calls[0]
    assert call["messages"][0]["content"] == "sys"  # no prompt hacks; the chat-template flag does it
    assert call["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False, "force_nonempty_content": True}}


def test_rpm_throttle_caps_requests_per_model(monkeypatch):
    monkeypatch.setattr(config, "RPM_PER_MODEL", 2)
    c, fake = client_with([_resp(), _resp()])
    chat(c)
    chat(c)
    assert len(c._req_times[config.MODELS["worker"]]) == 2  # a third call within the minute would wait


def test_think_tags_are_stripped():
    c, _ = client_with([_resp("<think>long reasoning</think>\nanswer")])
    r = chat(c)
    assert r.text == "answer" and "long reasoning" in r.reasoning


def test_spend_cap_stops_calls(monkeypatch):
    monkeypatch.setattr(config, "SPEND_CAP_USD", 0.0)
    c, fake = client_with([_resp()])
    with pytest.raises(llm.SpendCapExceeded):
        chat(c)
    assert fake.calls == []


def test_builder_propagates_fatal_and_marks_transient_errors():
    playbook.ensure_v0()
    pb = playbook.load("builder", 0)
    p = load_problems()["Prob001_zero"]
    c, _ = client_with([_err(openai.NotFoundError, 404)])
    with pytest.raises(llm.FatalLLMError):
        asyncio.run(build(p, pb, c))
    c, _ = client_with([_err(openai.RateLimitError, 429)] * (config.LLM_MAX_RETRIES + 1))
    r = asyncio.run(build(p, pb, c))
    assert r.error and r.code is None


def test_cache_reruns_only_errored_items():
    calls = []

    async def compute(ids, on_row):
        calls.append(list(ids))
        out = {i: {"passed": True, "error": "api down" if (len(calls) == 1 and i == "b") else None} for i in ids}
        for k, v in out.items():
            on_row(k, v)
        return out

    path = store.runs_dir() / "cache" / "x.json"
    first = asyncio.run(gatekeeper.cached_rows(path, "fp", "s", ["a", "b", "c"], compute))
    assert first["b"]["error"]
    second = asyncio.run(gatekeeper.cached_rows(path, "fp", "s", ["a", "b", "c"], compute))
    assert calls == [["a", "b", "c"], ["b"]] and not second["b"]["error"]
    asyncio.run(gatekeeper.cached_rows(path, "fp", "other-settings", ["a", "b", "c"], compute))
    assert calls[-1] == ["a", "b", "c"]  # changed settings invalidate the cache


def test_coach_tool_code_from_separate_block():
    text = ('Here are my proposals.\n```json\n{"proposals": [{"change_type": "tool_add", "tool_name": "lint", '
            '"tool_code": "see block", "summary": "s", "reasoning": "r", "evidence_problems": []}]}\n```\n'
            "```python\n# tool: lint\nimport re\n\ndef run(spec, verilog, ports):\n    return {\"fired\": False, \"findings\": []}\n```\n")
    props = parse_proposals(text, 2)
    assert props[0]["tool_code"].startswith("import re") and "def run" in props[0]["tool_code"]
    with pytest.raises(ValueError):
        parse_proposals("I have no proposals today.", 1)


def test_extract_code_prefers_the_design_over_a_testbench():
    text = ("```verilog\nmodule TopModule(input a, output y);\n  assign y = a;\nendmodule\n```\n"
            "And a quick test:\n```verilog\nmodule tb;\n  TopModule dut(.a(1'b0), .y());\nendmodule\n```\n")
    assert "assign y = a" in llm.extract_code(text)


def test_builder_think_setting_reaches_the_api():
    playbook.ensure_v0()
    pb = playbook.load("builder", 0).clone()
    assert pb.params["think"] == "low"  # thinking is part of the v0 baseline
    pb.params["think"] = "on"
    code = "```verilog\nmodule TopModule(output zero);\n  assign zero = 1'b0;\nendmodule\n```"
    c, fake = client_with([_resp(code)])
    asyncio.run(build(load_problems()["Prob001_zero"], pb, c))
    kw = fake.calls[0]["extra_body"]["chat_template_kwargs"]
    assert kw["enable_thinking"] is True and "low_effort" not in kw
    assert fake.calls[0]["max_tokens"] == config.THINKING_MAX_TOKENS


def test_coach_can_set_think_but_not_garbage():
    from engine import coach

    playbook.ensure_v0()
    pb = playbook.load("builder", 0)
    cand, err = coach.apply(pb, {"change_type": "param", "param": "think", "value": "on"}, [], "c")
    assert err is None and cand.params["think"] == "on"
    _, err = coach.apply(pb, {"change_type": "param", "param": "think", "value": "max"}, [], "c")
    assert err and "one of" in err
