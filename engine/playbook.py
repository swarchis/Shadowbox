"""Playbooks (what each team learns), their version folders, the lineage log, and tool stats.

Layout (see docs/CONTRACT.md):
  VERSIONS_DIR/<team>/v<n>/playbook.json, VERSIONS_DIR/<team>/v<n>/tools/<name>.py
  VERSIONS_DIR/<team>/candidates/<id>/...   proposals under test (kept for inspection)
  VERSIONS_DIR/<team>/current.json          {"version": n}
  VERSIONS_DIR/lineage.json                 {"entries": [...]}
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import prompts, store

TEAMS = ("builder", "breaker")


@dataclass
class Playbook:
    team: str
    version: int | str  # int for accepted versions; a string id for candidates
    parent: int | None = None
    created_round: int | None = None
    prompts: dict[str, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    # Verified solutions the team has collected: [{"problem_id", "spec", "code", "round"}]. Part of the playbook,
    # so it is versioned, gated and travels with it (transfer to another model included).
    memory: list[dict] = field(default_factory=list, repr=False)
    tool_sources: dict[str, str] = field(default_factory=dict, repr=False)  # not stored in playbook.json

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("tool_sources")
        return d

    def fingerprint(self) -> str:
        blob = json.dumps({**self.to_json(), "version": None, "parent": None, "created_round": None,
                           "tool_sources": self.tool_sources}, sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:10]

    def rules_block(self) -> str:
        if not self.rules:
            return ""
        lines = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(self.rules))
        return f"\n\nTeam playbook rules (follow all of them):\n{lines}"

    def system_prompt(self, role: str) -> str:
        return self.prompts[role] + self.rules_block()

    def clone(self) -> "Playbook":
        return copy.deepcopy(self)


def team_dir(team: str) -> Path:
    if team not in TEAMS:
        raise ValueError(team)
    return store.versions_dir() / team


def _write(pb: Playbook, folder: Path) -> None:
    """Build the version folder beside its final location, then rename it into place, so a crash
    never leaves a half-written (or empty) version behind."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    tmp = folder.parent / f".{folder.name}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "tools").mkdir(parents=True)
    for name in pb.tools:
        (tmp / "tools" / f"{name}.py").write_text(pb.tool_sources[name])
    store.write_json(tmp / "playbook.json", pb.to_json())
    if folder.exists():
        shutil.rmtree(folder)
    os.replace(tmp, folder)


def _read(folder: Path) -> Playbook:
    data = json.loads((folder / "playbook.json").read_text())
    pb = Playbook(**data)
    pb.tool_sources = {n: (folder / "tools" / f"{n}.py").read_text() for n in pb.tools}
    return pb


def default_playbook(team: str) -> Playbook:
    base = prompts.BUILDER_V0 if team == "builder" else prompts.BREAKER_V0
    return Playbook(team=team, version=0, prompts=dict(base["prompts"]), params=dict(base["params"]))


def ensure_v0() -> None:
    """Write the v0 playbooks. If prompts.py changed since v0 was written (e.g. after a smoke test) and
    no change has been proposed yet, refresh v0 so the run uses the current baseline. Result caches are
    keyed on the playbook fingerprint, so stale v0 results are recomputed automatically."""
    fresh_run = not read_lineage()
    for team in TEAMS:
        path = team_dir(team) / "v0" / "playbook.json"
        default = default_playbook(team)
        if not path.exists():
            _write(default, team_dir(team) / "v0")
        elif fresh_run and _read(team_dir(team) / "v0").fingerprint() != default.fingerprint():
            _write(default, team_dir(team) / "v0")
            store.event("v0_refreshed", f"{team.title()} v0 playbook refreshed from engine/prompts.py")
        if not (team_dir(team) / "current.json").exists():
            store.write_json(team_dir(team) / "current.json", {"version": 0})


def load(team: str, version: int) -> Playbook:
    return _read(team_dir(team) / f"v{version}")


def current_version(team: str) -> int:
    return int((store.read_json(team_dir(team) / "current.json", {"version": 0}) or {}).get("version", 0))


def load_current(team: str) -> Playbook:
    return load(team, current_version(team))


def save_candidate(pb: Playbook) -> Path:
    folder = team_dir(pb.team) / "candidates" / str(pb.version)
    _write(pb, folder)
    return folder


def promote(candidate: Playbook, round_no: int) -> int:
    """Store an accepted candidate as the next numbered version and make it current."""
    existing = [int(p.name[1:]) for p in team_dir(candidate.team).glob("v*")
                if re.fullmatch(r"v\d+", p.name) and (p / "playbook.json").exists()]
    new_v = max(existing, default=0) + 1
    pb = candidate.clone()
    pb.version, pb.created_round = new_v, round_no
    _write(pb, team_dir(pb.team) / f"v{new_v}")
    store.write_json(team_dir(pb.team) / "current.json", {"version": new_v})
    return new_v


def best_version(team: str) -> int:
    """The current version is always the best: changes are only accepted when they beat it."""
    return current_version(team)


# ------------------------------------------------------------------ lineage
def lineage_path() -> Path:
    return store.versions_dir() / "lineage.json"


def read_lineage() -> list[dict]:
    return (store.read_json(lineage_path(), {"entries": []}) or {}).get("entries", [])


def append_lineage(entries: list[dict]) -> None:
    all_entries = read_lineage()
    ids = {e["id"] for e in entries}
    all_entries = [e for e in all_entries if e["id"] not in ids] + entries
    store.write_json(lineage_path(), {"entries": all_entries})


def history_for_coach(team: str, limit: int = 12) -> str:
    rows = [e for e in read_lineage() if e["team"] == team][-limit:]
    if not rows:
        return "No previous proposals."
    def outcome(e):
        if e.get("invalid_reason"):
            return f"invalid, not tested: {e['invalid_reason']}"
        if e.get("net_flips") is None:
            return "not evaluated"
        return f"fixed {len(e.get('gained') or [])}, broke {len(e.get('lost') or [])}, net {e['net_flips']:+d}"

    return "\n".join(
        f"- round {e['round']}: [{'ACCEPTED' if e['accepted'] else 'rejected'}] {e['change_type']}: {e['summary']} ({outcome(e)})"
        for e in rows
    )


# ------------------------------------------------------------------ tool stats
def tool_stats_path(team: str) -> Path:
    return team_dir(team) / "tool_stats.json"


def record_tool_use(team: str, reports: list[dict], born_round: dict[str, int] | None = None) -> None:
    if not reports:
        return
    stats = store.read_json(tool_stats_path(team), {}) or {}
    for r in reports:
        s = stats.setdefault(r["tool"], {"runs": 0, "fired": 0, "errors": 0, "born_round": (born_round or {}).get(r["tool"])})
        s["runs"] += 1
        s["fired"] += int(bool(r.get("fired")))
        s["errors"] += int(bool(r.get("error")))
    store.write_json(tool_stats_path(team), stats)


def set_tool_born(team: str, name: str, round_no: int) -> None:
    stats = store.read_json(tool_stats_path(team), {}) or {}
    stats.setdefault(name, {"runs": 0, "fired": 0, "errors": 0})["born_round"] = round_no
    store.write_json(tool_stats_path(team), stats)
