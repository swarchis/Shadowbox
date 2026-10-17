"""Frozen bug pool: real buggy designs written by Builder v0 on validation problems.

Built once and never changed, so the Breaker's catch rate on it measures skill rather than
how buggy the current Builder happens to be.
"""
from __future__ import annotations

import asyncio
import hashlib

from . import config, harness, store
from .dataset import Problem
from .gatekeeper import builder_results_cached
from .llm import LLMClient
from .playbook import Playbook


def pool_path():
    return store.runs_dir() / "bug_pool.json"


_session_pool: list[dict] | None = None  # an unfrozen pool, usable for this process only


def load_pool() -> list[dict]:
    entries = (store.read_json(pool_path(), {}) or {}).get("entries")
    return entries if entries else (_session_pool or [])


async def build_pool(val_problems: list[Problem], builder_v0: Playbook, v0_val: dict[str, dict], llm: LLMClient) -> list[dict]:
    """Frozen once built from error-free results. If any source build hit an API error, the pool is
    returned for this session but NOT frozen, so a rerun rebuilds it after the errored builds are retried."""
    existing = store.read_json(pool_path())
    if existing and existing.get("entries"):
        return existing["entries"]
    sources = [v0_val]
    for k in range(config.BUG_POOL_EXTRA_DRAFTS):
        sources.append(await builder_results_cached(f"bugpool_extra{k}", val_problems, builder_v0, llm, tag=f"bugpool_extra{k}",
                                                    temperature=config.DRAFT_TEMPERATURE, draft_index=100 + k))
    errored = sum(bool(r.get("error")) for src in sources for r in src.values())
    candidates: list[tuple[str, str, str]] = []  # (problem_id, code, source)
    for k, src in enumerate(sources):
        label = "v0@temp0" if k == 0 else f"v0@temp{config.DRAFT_TEMPERATURE}"
        for pid, r in src.items():
            if r["code"] and r["compiled"] and not r["passed"] and not r.get("error"):
                candidates.append((pid, r["code"], label))
    seen, by_problem = set(), {}
    for pid, code, src in candidates:
        h = hashlib.sha1(code.encode()).hexdigest()[:12]
        if h in seen:
            continue
        seen.add(h)
        by_problem.setdefault(pid, []).append({"id": f"{pid}#{h}", "problem_id": pid, "code": code, "source": src})
    entries: list[dict] = []
    while len(entries) < config.BUG_POOL_MAX and any(by_problem.values()):  # round-robin keeps the pool diverse
        for pid in sorted(by_problem):
            if by_problem[pid] and len(entries) < config.BUG_POOL_MAX:
                entries.append(by_problem[pid].pop(0))
    problems = {p.id: p for p in val_problems}

    def random_catch(e):
        chk = harness.check_against_ref(problems[e["problem_id"]], e["code"], harness.random_stimulus(problems[e["problem_id"]], 40, seed=1))
        return chk.valid_bug

    flags = await asyncio.gather(*(asyncio.to_thread(random_catch, e) for e in entries))
    for e, f in zip(entries, flags):
        e["caught_by_random40"] = f
    global _session_pool
    if errored or not entries:
        _session_pool = entries
        store.event("bug_pool", f"Bug pool NOT frozen yet ({len(entries)} designs; {errored} source build(s) hit API errors). "
                    "It will be rebuilt on the next run.")
        return entries
    store.write_json(pool_path(), {"created_at": store.now_iso(), "entries": entries,
                                   "note": "Compiling Builder v0 designs that fail the official testbench. Frozen."})
    store.event("bug_pool", f"Frozen bug pool built: {len(entries)} buggy designs from {len({e['problem_id'] for e in entries})} problems")
    return entries
