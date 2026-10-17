"""Replay a finished run at speed, for demos. Clearly labelled: every state response carries `replay`.

Start with:  SHADOWBOX_REPLAY=runs_run5 SHADOWBOX_REPLAY_SPEED=20 python -m server.api
The server re-plays the run's own recorded timeline (events, rounds, gate results, ledger, final exam)
against a replay clock: replay_time = run_start + (now - replay_started) * speed. Nothing is invented;
every value shown is from the recorded run, revealed at the moment it originally happened.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def _ts(s: str | None) -> float | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl(path: Path) -> list[dict]:
    out = []
    try:
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        pass
    return out


def _step_from(event: dict) -> str | None:
    """Rough in-round step for the live panel's step bar, from the latest event type."""
    t = event.get("type", "")
    if t == "match_start":
        return "match"
    if t == "match_done":
        return "builder_coach"
    if t == "gate_result":
        return "builder_gate" if event.get("team") == "builder" else "breaker_gate"
    return "match"


class Replay:
    def __init__(self, runs: Path, speed: float):
        self.runs = runs
        self.speed = max(1.0, speed)
        self.events = _jsonl(runs / "events.jsonl")
        self.ledger = sorted(_jsonl(runs / "ledger.jsonl"), key=lambda r: r.get("ts", ""))
        times = [t for t in (_ts(e.get("ts")) for e in self.events) if t]
        self.start = min(times) if times else time.time()
        self.end = max(times) if times else self.start
        self.restart()

    def restart(self) -> None:
        """Back to the beginning, paused: the presenter presses Play when ready."""
        self.played = 0.0  # recorded seconds already played before the current play stretch
        self.wall0 = time.time()
        self.playing = False

    def play(self) -> None:
        if not self.playing:
            self.wall0 = time.time()
            self.playing = True

    def pause(self) -> None:
        if self.playing:
            self.played = self._played()
            self.playing = False

    def _played(self) -> float:
        extra = (time.time() - self.wall0) * self.speed if self.playing else 0.0
        return min(self.end + 1 - self.start, self.played + extra)

    def now(self) -> float:
        return self.start + self._played()

    def seen_events(self) -> list[dict]:
        t = self.now()
        return [e for e in self.events if (_ts(e.get("ts")) or 0) <= t]

    def happened(self, type_: str) -> float | None:
        t = self.now()
        for e in self.events:
            et = _ts(e.get("ts"))
            if e.get("type") == type_ and et and et <= t:
                return et
        return None

    def rounds_done(self) -> list[int]:
        t = self.now()
        out = []
        for e in self.events:
            if e.get("type") == "round_done" and (_ts(e.get("ts")) or 0) <= t and isinstance(e.get("round"), int):
                out.append(e["round"])
        return sorted(set(out))

    def info(self) -> dict:
        return {"active": True, "speed": self.speed, "playing": self.playing and self.now() < self.end, "recorded_started_at": _iso(self.start), "recorded_ended_at": _iso(self.end),
                "progress": round(min(1.0, (self.now() - self.start) / max(1.0, self.end - self.start)), 4),
                "elapsed_s": round(min(self.now(), self.end) - self.start, 1), "total_s": round(self.end - self.start, 1),
                "run": self.runs.name}

    # ---------------------------------------------------------------- endpoint transforms
    def state(self, recorded: dict) -> dict:
        t = self.now()
        seen = self.seen_events()
        in_final_now = any(e.get("type") == "final_start" for e in seen)
        # the held-out baselines run in a side lane from the start; their "Final exam: ..." lines would
        # read as if the exam had begun, so the headline message skips them until the exam really starts
        quiet = ("llm_retry", "llm_error", "api_errors", "resume_items") + (() if in_final_now else ("final_step",))
        last = next((e for e in reversed(seen) if e.get("type") not in quiet), {})
        done = self.rounds_done()
        rounds = [e["round"] for e in seen if isinstance(e.get("round"), int)]
        finished = any(e.get("type") in ("final_done", "hard_stop") for e in seen) or t >= self.end
        in_final = any(e.get("type") == "final_start" for e in seen)
        kept = {"builder": 0, "breaker": 0}
        for e in seen:
            if e.get("type") == "gate_result" and e.get("accepted") and e.get("team") in kept:
                kept[e["team"]] += 1
        spent = [r for r in self.ledger if (_ts(r.get("ts")) or 0) <= t]
        return {
            **recorded,
            "status": "finished" if finished else "running",
            "phase": "done" if finished else ("final" if in_final else ("round" if rounds else "setup")),
            "round": max(rounds) if rounds else 0,
            "step": "done" if finished else ("final" if in_final else (_step_from(last) if rounds else None)),
            "message": last.get("message", "Starting"),
            "started_at": _iso(self.start),
            "updated_at": _iso(t),
            "deadline_at": None,
            "spend_usd": round(sum(r.get("cost_usd", 0.0) for r in spent), 4),
            "llm_calls": len(spent),
            "builder_version": kept["builder"],
            "breaker_version": kept["breaker"],
            "rounds_completed": len(done),
            "replay": self.info(),
        }

    def series(self, data: dict) -> dict:
        done = set(self.rounds_done())
        last = max(done) if done else 0
        points = [p for p in data.get("points", []) if p.get("round") == 0 or p.get("round") in done]
        changes = [c for c in data.get("changes", []) if isinstance(c.get("round"), int) and c["round"] <= last]
        return {**data, "points": points, "changes": changes}

    def lineage(self, data: dict) -> dict:
        t = self.now()
        return {**data, "entries": [e for e in data.get("entries", []) if (_ts(e.get("ts")) or 0) <= t]}

    def rounds(self, data: dict) -> dict:
        done = set(self.rounds_done())
        seen_rounds = {e["round"] for e in self.seen_events() if isinstance(e.get("round"), int)}
        out = []
        for r in data.get("rounds", []):
            if r["round"] in done:
                out.append(r)
            elif r["round"] in seen_rounds:
                out.append({**r, "complete": False})
        return {"rounds": out}

    def final_visible(self) -> bool:
        return self.happened("final_done") is not None or self.happened("hard_stop") is not None or self.now() >= self.end

    def events_page(self, since: int) -> dict:
        seen = self.seen_events()
        return {"events": [{**e, "seq": i} for i, e in enumerate(seen) if i >= since], "next": len(seen)}

    def live_source(self) -> tuple[Path | None, str]:
        """Which recorded file the live view should show at this replay moment."""
        if self.happened("final_start") is not None:
            for name in ("test_vbest.json", "drafts_d0.json", "test_v0.json"):
                if (self.runs / "final" / name).exists():
                    return self.runs / "final" / name, "Final exam · latest version"
        done = self.rounds_done()
        current = (max(done) + 1) if done else 1
        for n in (current, current - 1):
            p = self.runs / f"round_{n}" / "match.json"
            started = any(e.get("type") == "match_start" and e.get("round") == n for e in self.seen_events())
            if p.exists() and (n in done or (n == current and started)):
                return p, f"Round {n} · training match"
        p = self.runs / "cache" / "builder_0_val.json"
        return (p if p.exists() else None), "Setup · Builder v0 on validation"

    def window(self, rows: list, size: int) -> list:
        """Step through the recorded rows over time so the feed keeps moving."""
        if len(rows) <= size:
            return rows
        offset = int(self._played() / self.speed / 2.5) % len(rows)
        return (rows[offset:] + rows[:offset])[:size]


def from_env(root: Path) -> Replay | None:
    name = os.environ.get("SHADOWBOX_REPLAY")
    if not name:
        return None
    runs = (root / name) if not os.path.isabs(name) else Path(name)
    return Replay(runs, float(os.environ.get("SHADOWBOX_REPLAY_SPEED", "20")))
