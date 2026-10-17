"""Evaluation helpers and the paired accept/reject rule.

Builder changes are judged on the validation split with the official testbenches.
Breaker changes are judged on the frozen bug pool. Both use paired comparison on the same items:
accept the best candidate only if (newly passing - newly failing) >= GATE_MARGIN.
"""
from __future__ import annotations

import asyncio

from . import config, harness, store
from .breaker import attack
from .builder import build
from .dataset import Problem, load_problems
from .llm import LLMClient
from .playbook import Playbook


def cache_path(name: str):
    return store.runs_dir() / "cache" / f"{name}.json"


def settings_key(model_key: str = "worker", temperature: float = config.WORK_TEMPERATURE) -> str:
    """Everything besides the playbook that changes results; part of every cache key."""
    return (f"model={config.MODELS.get(model_key, model_key)}|t={temperature}|think={config.WORKER_THINKING}"
            f"|mock={config.MOCK}")


async def cached_rows(path, fingerprint: str, settings: str, ids: list[str], compute) -> dict[str, dict]:
    """Result cache keyed on (playbook fingerprint, run settings, item ids).

    compute(ids, on_row) must call on_row(id, row) as each item finishes: finished rows are saved
    as they arrive, so an interruption (Ctrl-C, hard stop, spend cap) never throws away work that was
    already paid for. Rows that errored (API failures) are never trusted and are recomputed."""
    import time as _time

    hit = store.read_json(path)
    rows: dict[str, dict] = {}
    if hit and hit.get("fingerprint") == fingerprint and hit.get("settings") == settings:
        rows = {k: v for k, v in hit.get("results", {}).items() if k in ids}
    todo = sorted(i for i in ids if i not in rows or rows[i].get("error"))
    if not todo:
        return {i: rows[i] for i in ids}
    if rows:
        store.event("resume_items", f"Reusing {len(ids) - len(todo)} saved item(s), computing {len(todo)} ({path.name})")
    last_save = [0.0]

    def save(final: bool = False):
        store.write_json(path, {"fingerprint": fingerprint, "settings": settings, "results": rows, "complete": final})

    def on_row(k: str, row: dict):
        rows[k] = row
        if _time.monotonic() - last_save[0] > 2.0:
            last_save[0] = _time.monotonic()
            save()

    await compute(todo, on_row)
    save(final=True)
    res = {i: rows[i] for i in ids}
    n_err = sum(bool(r.get("error")) for r in res.values())
    if n_err:
        store.event("api_errors", f"{n_err} of {len(res)} item(s) in {path.name} failed with API errors; excluded from scores, retried on rerun")
    return res


async def run_builder_on(problems: list[Problem], pb: Playbook, llm: LLMClient, *, tag: str, model_key: str = "worker",
                         temperature: float = config.WORK_TEMPERATURE, draft_index: int = 0, on_row=None) -> dict[str, dict]:
    """Build every problem and grade it with the official testbench. on_row(id, row) fires as each finishes."""

    async def one(p: Problem) -> dict:
        b = await build(p, pb, llm, temperature=temperature, model_key=model_key, tag=tag, draft_index=draft_index)
        off = await asyncio.to_thread(harness.run_official, p, b.code) if b.code else None
        return {
            "problem_id": p.id,
            "passed": bool(off and off.passed),
            "kind": off.kind if off else ("api_error" if b.error else "no_code"),
            "mismatches": off.mismatches if off else None,
            "compiled": b.compiled,
            "code": b.code,
            "attempts": b.attempts,
            "error": b.error,
            "cost_usd": round(b.cost_usd, 6),
        }

    async def tracked(p: Problem) -> dict:
        row = await one(p)
        if on_row:
            on_row(p.id, row)
        return row

    rows = await asyncio.gather(*(tracked(p) for p in problems))
    return {r["problem_id"]: r for r in rows}


async def builder_results_cached(name: str, problems: list[Problem], pb: Playbook, llm: LLMClient, *, tag: str,
                                 model_key: str = "worker", temperature: float = config.WORK_TEMPERATURE,
                                 draft_index: int = 0) -> dict[str, dict]:
    by_id = {p.id: p for p in problems}

    async def compute(ids, on_row):
        return await run_builder_on([by_id[i] for i in ids], pb, llm, tag=tag, model_key=model_key,
                                    temperature=temperature, draft_index=draft_index, on_row=on_row)

    return await cached_rows(cache_path(name), pb.fingerprint(), settings_key(model_key, temperature), sorted(by_id), compute)


async def run_breaker_on_pool(pool: list[dict], pb: Playbook, llm: LLMClient, *, tag: str, on_row=None) -> dict[str, dict]:
    """Attack every frozen buggy design; 'caught' means the reference confirms a real mismatch."""
    problems = load_problems()

    async def one(entry: dict) -> dict:
        p = problems[entry["problem_id"]]
        a = await attack(p, entry["code"], pb, llm, tag=tag)
        caught, first = False, None
        if a.stimulus:
            chk = await asyncio.to_thread(harness.check_against_ref, p, entry["code"], a.stimulus)
            caught, first = chk.valid_bug, chk.first_mismatch
        row = {"id": entry["id"], "problem_id": p.id, "caught": caught, "cycles": len(a.stimulus or []),
               "error": a.error if a.api_error else None, "attack_error": a.error, "first_mismatch": first}
        if on_row:
            on_row(entry["id"], row)
        return row

    rows = await asyncio.gather(*(one(e) for e in pool))
    return {r["id"]: r for r in rows}


async def breaker_results_cached(name: str, pool: list[dict], pb: Playbook, llm: LLMClient, *, tag: str) -> dict[str, dict]:
    by_id = {e["id"]: e for e in pool}

    async def compute(ids, on_row):
        return await run_breaker_on_pool([by_id[i] for i in ids], pb, llm, tag=tag, on_row=on_row)

    return await cached_rows(cache_path(name), pb.fingerprint(), settings_key(), sorted(by_id), compute)


def score(results: dict[str, dict], key: str) -> float:
    """Pass/catch rate over items that did not hit an API error."""
    ok = [r for r in results.values() if not r.get("error")]
    return sum(bool(r[key]) for r in ok) / max(1, len(ok))


def n_errors(results: dict[str, dict]) -> int:
    return sum(bool(r.get("error")) for r in results.values())


def flips(current: dict[str, dict], cand: dict[str, dict], key: str) -> tuple[list[str], list[str], int]:
    """Paired comparison on the same items, skipping items that errored on either side.
    key = 'passed' (builder) or 'caught' (breaker)."""
    both = [i for i in cand if i in current and not cand[i].get("error") and not current[i].get("error")]
    gained = sorted(i for i in both if cand[i][key] and not current[i][key])
    lost = sorted(i for i in both if not cand[i][key] and current[i][key])
    return gained, lost, len(gained) - len(lost)


MAX_GATE_ERRORS = 3  # more errored items than this on either side and the comparison isn't trusted


def decide(evaluated: list[dict]) -> dict | None:
    """Pick the best candidate by net flips (ties: fewer losses); accept only if it clears the margin
    and the comparison wasn't degraded by API errors."""
    ok = [e for e in evaluated if e.get("net_flips") is not None and e.get("errors", 0) <= MAX_GATE_ERRORS]
    if not ok:
        return None
    best = max(ok, key=lambda e: (e["net_flips"], -len(e["lost"])))
    return best if passes(best) else None


def passes(e: dict) -> bool:
    """Keep a change if it clears the margin, or if it is a clean win: fixes several, breaks none."""
    return e["net_flips"] >= config.GATE_MARGIN or (len(e["gained"]) >= config.CLEAN_WIN_MIN and not e["lost"])
