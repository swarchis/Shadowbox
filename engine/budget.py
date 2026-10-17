"""Wall-clock budget for a time-boxed run, with estimates calibrated from measured throughput.

`--minutes M` sets a target deadline. The loop stops starting rounds when a round plus the required
final exam would not fit; the final exam drops optional work and extra drafts as time runs short;
and at deadline + grace the whole run is cancelled (finished steps stay saved, results are assembled
from whatever completed).
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

from . import config, store


class Budget:
    def __init__(self, minutes: float | None = None, grace_minutes: float = 5.0):
        self.t0 = time.monotonic()
        self.minutes = minutes
        self.grace_s = grace_minutes * 60
        self.deadline = self.t0 + minutes * 60 if minutes else None
        self.deadline_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ") if minutes else None

    @property
    def enabled(self) -> bool:
        return self.deadline is not None

    def left(self) -> float:
        """Seconds until the target deadline (inf without a budget)."""
        return math.inf if self.deadline is None else self.deadline - time.monotonic()

    def hard_left(self) -> float:
        """Seconds until the hard stop (deadline + grace)."""
        return math.inf if self.deadline is None else self.deadline + self.grace_s - time.monotonic()

    def fits(self, seconds: float, safety: float = 1.15) -> bool:
        return seconds * safety <= self.left()


BUDGET = Budget(None)


def set_budget(minutes: float | None, grace_minutes: float = 5.0) -> Budget:
    global BUDGET
    BUDGET = Budget(minutes, grace_minutes)
    return BUDGET


# ------------------------------------------------------------------ throughput from the ledger
# Unit of work: one Builder build (counted by its writer call) or one Breaker attack, weighted 0.6.
# Measuring finished work rather than raw LLM calls captures every bottleneck (rate limits, latency,
# simulator CPU time), whichever dominates.
ATTACK_WEIGHT = 0.6


def _ts(row) -> float:
    try:
        return datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (KeyError, ValueError):
        return 0.0


def _work(row) -> float:
    role = row.get("role")
    if role == "writer":
        return 1.0
    if role in ("attacker", "multi_attacker"):
        return ATTACK_WEIGHT
    return 0.0


def work_per_second(window_s: float = 300.0) -> float | None:
    """Recent finished work items per second while work was actually happening.

    Measured over the `window_s` seconds before the most recent finished item (not before "now"),
    so a pause between a crash and a resume doesn't count as slowness."""
    rows = [r for r in store.read_jsonl(store.ledger_path()) if _work(r)]
    if len(rows) < 10:
        return None
    stamps = sorted(_ts(r) for r in rows)
    last = stamps[-1]
    recent = [t for t in stamps if t >= last - window_s]
    if len(recent) < 10:
        recent = stamps[-60:]
    weights = sorted(((_ts(r), _work(r)) for r in rows if _ts(r) >= recent[0]), key=lambda x: x[0])
    # gaps longer than 2 minutes with nothing finishing are idle time (process stopped), not work time
    span, prev = 0.0, None
    for t, _ in weights:
        if prev is not None:
            span += min(t - prev, 120.0)
        prev = t
    return sum(w for _, w in weights) / max(span, 1.0)


def calls_per_build() -> float:
    """Average LLM calls per Builder build (writer + debugger + planner), measured; 1.8 until known."""
    rows = store.read_jsonl(store.ledger_path())
    writers = sum(r.get("role") == "writer" for r in rows)
    if writers < 5:
        return 1.8
    return sum(r.get("role") in ("writer", "debugger", "planner") for r in rows) / writers


def builds_done(tag_prefix: str) -> int:
    rows = store.read_jsonl(store.ledger_path())
    return sum(r.get("role") == "writer" and str(r.get("tag", "")).startswith(tag_prefix) for r in rows)


def seconds_for_work(items: float) -> float:
    """Wall time for this much work at the measured rate; conservative before any measurement."""
    wps = work_per_second()
    if not wps:
        wps = config.LLM_CONCURRENCY / 40.0  # assume ~40 s per build before we have data
    return items / wps


def final_work(n_test: int, n_drafts: int, *, vbest_needed: bool = True, optional: bool = False, v0_pending: bool = False) -> float:
    """Work items for the final exam: drafts, vBest, one Breaker attack per problem (+ demo cases)."""
    work = n_test * n_drafts + n_test * ATTACK_WEIGHT * 1.2 + 4
    if vbest_needed:
        work += n_test
    if v0_pending:
        work += max(0, n_test - builds_done("final:test_v0"))
    if optional:
        work += n_test + n_test * ATTACK_WEIGHT * 1.2  # transfer-after + Breaker-v0 selection
    return work


def fmt(seconds: float) -> str:
    return "∞" if math.isinf(seconds) else f"{seconds / 60:.1f} min"
