"""Read-only FastAPI server over the engine's plain JSON files.

Every response shape is defined in docs/CONTRACT.md. The server never writes anything.
Missing, partial or unreadable files are treated as absent and produce an empty-but-valid
body, so the UI can always render ("waiting for first round") instead of erroring.

Paths come from engine.config and are read as attributes on every request
(config.RUNS_DIR, not a copied value) so tests and the engine can repoint them.

Run:  python -m server.api        (SHADOWBOX_HOST / SHADOWBOX_PORT override 127.0.0.1:8000)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:  # allow `python server/api.py` and runs from other folders
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

from engine import config  # noqa: E402
from server import replay as _replay_mod  # noqa: E402

REPLAY: "_replay_mod.Replay | None" = None  # set by choose_data_dirs when SHADOWBOX_REPLAY is set

TEAMS = ("builder", "breaker")
_ROUND_DIR_RE = re.compile(r"^round_(\d+)$")
_VERSION_DIR_RE = re.compile(r"^v(\d+)$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_MAX_TOOL_SOURCE_BYTES = 200_000

FINAL_METRIC_KEYS = (
    "v0", "vbest", "vbest_selection", "random_pick", "random_input_sel", "breaker_v0_sel",
    "ceiling", "ultra", "transfer_v0", "transfer_vbest", "ablation_nano_coach", "ablation_main_coach",
)
VERSION_PAIR_KEYS = ("v0", "vbest")
EVENT_DEFAULTS = {"ts": None, "type": "", "round": None, "team": None, "message": ""}
SUMMARY_KEYS = ("train_pass", "hard_pass", "bugs_found", "subtle_bugs", "problems")

# ------------------------------------------------------------------ paths (read at request time)


def _runs_dir() -> Path:
    return Path(config.RUNS_DIR)


def _versions_dir() -> Path:
    return Path(config.VERSIONS_DIR)


def _root_dir() -> Path:
    return Path(config.ROOT)


def _mode() -> str:
    """The run's own mode (written by the engine into state.json) wins over this process's config."""
    st = _read_json(_runs_dir() / "state.json")
    if isinstance(st, dict) and st.get("mode") in ("mock", "real"):
        return st["mode"]
    return "mock" if getattr(config, "MOCK", False) else "real"


# ------------------------------------------------------------------ safe readers


def _read_json(path: Path) -> Any:
    """Parsed JSON, or None if the file is missing, partial, unreadable or not JSON."""
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - any failure means "treat as missing"
        return None


def _read_obj(path: Path) -> dict:
    data = _read_json(path)
    return data if isinstance(data, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _dict_items(value: Any) -> list[dict]:
    """The list's object items only: a stray string or number in an array must not crash the UI."""
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _fill(data: dict, defaults: dict) -> dict:
    """Defaults for keys that are missing (or null when the default is not null)."""
    out = dict(data)
    for key, default in defaults.items():
        if out.get(key) is None and default is not None:
            out[key] = default
        else:
            out.setdefault(key, default)
    return out


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _numbered_dirs(parent: Path, pattern: re.Pattern) -> list[tuple[int, Path]]:
    """[(n, path)] for child dirs whose name matches pattern, sorted by n."""
    found = []
    try:
        for child in parent.iterdir():
            m = pattern.match(child.name)
            if m and child.is_dir():
                found.append((int(m.group(1)), child))
    except OSError:
        return []
    found.sort(key=lambda item: item[0])
    return found


def _check_team(team: str) -> str:
    if team not in TEAMS:
        raise HTTPException(status_code=400, detail=f"team must be one of {list(TEAMS)}")
    return team


# ------------------------------------------------------------------ app

app = FastAPI(title="Shadowbox API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
              redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_api(request: Request, call_next):
    """The UI polls; never let a browser or proxy serve a stale run state."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ------------------------------------------------------------------ /api/state


def _default_splits() -> dict:
    data = _read_obj(Path(getattr(config, "SPLITS_PATH", _root_dir() / "data" / "splits.json")))
    splits = {}
    for name in ("train", "val", "test"):
        value = data.get(name)
        splits[name] = len(value) if isinstance(value, list) else 0
    return splits


@app.get("/api/state")
def get_state() -> dict:
    state = _read_obj(_runs_dir() / "state.json")
    defaults = {
        "mode": _mode(),
        "status": "idle",
        "phase": "setup",
        "round": 0,
        "step": None,
        "message": "",
        "started_at": None,
        "updated_at": None,
        "deadline_at": None,
        "spend_usd": 0.0,
        "spend_cap_usd": float(getattr(config, "SPEND_CAP_USD", 0.0)),
        "llm_calls": 0,
        "human_interventions": 0,
        "builder_version": 0,
        "breaker_version": 0,
        "splits": None,
    }
    out = _fill(state, defaults)
    if not isinstance(out.get("splits"), dict) or not out["splits"]:
        out["splits"] = _default_splits()
    if REPLAY:
        out = REPLAY.state(out)
    return out


_REPLAY_NAME_RE = re.compile(r"^runs(_[A-Za-z0-9]+)?$")


def _replayable_runs() -> list[dict]:
    """Finished or running real runs that have a timeline and a chart (mock and aborted folders are left out)."""
    out = []
    for d in sorted(_root_dir().glob("runs*")):
        if not d.is_dir() or not _REPLAY_NAME_RE.match(d.name) or "mock" in d.name:
            continue
        if not ((d / "events.jsonl").is_file() and (d / "series.json").is_file()):
            continue
        series = _read_obj(d / "series.json")
        pts = _dict_items(series.get("points"))
        if len(pts) < 2 or (len(pts) < 4 and d.name != "runs" and not (d / "final" / "final.json").is_file()):
            continue  # aborted attempts: too short to be worth replaying
        first, last = pts[0], pts[-1]
        out.append({"run": d.name, "label": "latest run" if d.name == "runs" else d.name.replace("runs_", "").replace("run", "run "),
                    "rounds": len(pts) - 1, "builder": [first.get("builder_val_pass"), last.get("builder_val_pass")],
                    "breaker": [first.get("breaker_pool_catch"), last.get("breaker_pool_catch")]})
    return out


@app.get("/api/replay/runs")
def list_replay_runs() -> dict:
    return {"current": REPLAY.runs.name if REPLAY else None, "runs": _replayable_runs() if REPLAY else []}


@app.post("/api/replay/select")
def select_replay_run(run: str = Query(...)) -> dict:
    global REPLAY
    if not REPLAY:
        raise HTTPException(status_code=404, detail="Not in replay mode")
    if run not in {r["run"] for r in _replayable_runs()}:
        raise HTTPException(status_code=400, detail="Unknown run")
    runs = _root_dir() / run
    config.RUNS_DIR = runs
    config.VERSIONS_DIR = runs.parent / runs.name.replace("runs", "versions", 1)
    REPLAY = _replay_mod.Replay(runs, REPLAY.speed)
    return REPLAY.info()


@app.post("/api/replay/play")
def play_replay() -> dict:
    if not REPLAY:
        raise HTTPException(status_code=404, detail="Not in replay mode")
    REPLAY.play()
    return REPLAY.info()


@app.post("/api/replay/pause")
def pause_replay() -> dict:
    if not REPLAY:
        raise HTTPException(status_code=404, detail="Not in replay mode")
    REPLAY.pause()
    return REPLAY.info()


@app.post("/api/replay/restart")
def restart_replay() -> dict:
    if not REPLAY:
        raise HTTPException(status_code=404, detail="Not in replay mode")
    REPLAY.restart()
    return REPLAY.info()


# ------------------------------------------------------------------ simple file-backed endpoints


@app.get("/api/series")
def get_series() -> dict:
    data = _read_obj(_runs_dir() / "series.json")
    out = {**data, "points": _dict_items(data.get("points")), "changes": _dict_items(data.get("changes"))}
    return REPLAY.series(out) if REPLAY else out


@app.get("/api/lineage")
def get_lineage() -> dict:
    data = _read_obj(_versions_dir() / "lineage.json")
    out = {**data, "entries": _dict_items(data.get("entries"))}
    return REPLAY.lineage(out) if REPLAY else out


def _version_pair(value: Any) -> dict:
    """{"v0": n, "vbest": n}; keys the engine has not written yet are null."""
    return {**{key: None for key in VERSION_PAIR_KEYS}, **_as_dict(value)}


@app.get("/api/final")
def get_final() -> dict:
    data = _read_obj(_runs_dir() / "final" / "final.json") if not REPLAY or REPLAY.final_visible() else {}
    metrics = {key: (value if isinstance(value, dict) else None) for key, value in _as_dict(data.get("metrics")).items()}
    metrics = {**{key: None for key in FINAL_METRIC_KEYS}, **metrics}
    out = _fill(data, {
        "complete": False,
        "test_problems": None,
        "n_drafts": None,
        "cost_usd": None,
        "notes": [],
    })
    out["metrics"] = metrics
    out["builder_versions"] = _version_pair(data.get("builder_versions"))
    out["breaker_versions"] = _version_pair(data.get("breaker_versions"))
    out["notes"] = [n for n in _as_list(out.get("notes")) if isinstance(n, str)]
    return out


@app.get("/api/selection-examples")
def get_selection_examples() -> dict:
    data = _read_obj(_runs_dir() / "final" / "selection_examples.json") if not REPLAY or REPLAY.final_visible() else {}
    return {**data, "examples": _dict_items(data.get("examples"))}


@app.get("/api/demo-cases")
def get_demo_cases() -> dict:
    data = _read_obj(_runs_dir() / "final" / "demo_cases.json") if not REPLAY or REPLAY.final_visible() else {}
    return {**data, "cases": _dict_items(data.get("cases"))}


@app.get("/api/demo-config")
def get_demo_config() -> dict:
    data = _read_obj(_root_dir() / "demo.json")
    out = _fill(data, {
        "project": "Shadowbox",
        "tagline": "AI teams that get better by fighting themselves",
        "team": [],
        "repo_url": None,
    })
    out["team"] = [
        {**m, "name": str(m.get("name") or ""), "photo": m.get("photo") if isinstance(m.get("photo"), str) else None}
        for m in _dict_items(out.get("team"))
    ]
    return out


# ------------------------------------------------------------------ rounds


def _summary(match: dict) -> dict:
    summary = _as_dict(match.get("summary"))
    out = {key: summary.get(key) for key in SUMMARY_KEYS}
    if out["problems"] is None and isinstance(match.get("problems"), list):
        out["problems"] = len(match["problems"])
    return {**summary, **out}


@app.get("/api/rounds")
def get_rounds() -> dict:
    rounds = []
    for n, path in _numbered_dirs(_runs_dir(), _ROUND_DIR_RE):
        match = _read_obj(path / "match.json")
        summary = _summary(match)
        rounds.append({
            "round": n,
            "complete": (path / "done.json").is_file(),
            "builder_version": match.get("builder_version"),
            "breaker_version": match.get("breaker_version"),
            **{key: summary[key] for key in SUMMARY_KEYS},
        })
    return REPLAY.rounds({"rounds": rounds}) if REPLAY else {"rounds": rounds}


@app.get("/api/rounds/{n}/match")
def get_round_match(n: int) -> dict:
    match = _read_obj(_runs_dir() / f"round_{n}" / "match.json") if n >= 0 else {}
    if REPLAY and n not in REPLAY.rounds_done():
        match = {}
    out = _fill(match, {"round": n, "builder_version": None, "breaker_version": None})
    out["summary"] = _summary(match)
    out["problems"] = [p for p in _as_list(match.get("problems")) if isinstance(p, dict)]
    return out


# ------------------------------------------------------------------ playbooks


def _team_versions(team: str) -> list[tuple[int, Path]]:
    return _numbered_dirs(_versions_dir() / team, _VERSION_DIR_RE)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


@app.get("/api/playbooks/{team}")
def get_playbooks(team: str) -> dict:
    _check_team(team)
    versions = []
    for n, path in _team_versions(team):
        playbook = _read_obj(path / "playbook.json")
        versions.append({
            "version": n,
            "parent": playbook.get("parent"),
            "rules": len(_as_list(playbook.get("rules"))),
            "tools": len(_as_list(playbook.get("tools"))),
            "created_round": playbook.get("created_round"),
        })
    current = _int_or_none(_read_obj(_versions_dir() / team / "current.json").get("version"))
    if current is None:
        current = versions[-1]["version"] if versions else 0
    return {"team": team, "current": current, "versions": versions}


def _tool_sources(version_dir: Path, tool_names: list) -> dict:
    tools_dir = version_dir / "tools"
    sources = {}
    for name in tool_names:
        if not isinstance(name, str) or not _TOOL_NAME_RE.match(name):
            continue  # tool names come from LLM output: never let one become a path
        path = tools_dir / f"{name}.py"
        if not _is_within(path, tools_dir):
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read(_MAX_TOOL_SOURCE_BYTES)
            sources[name] = raw.decode("utf-8", errors="replace")
        except OSError:
            continue
    return sources


@app.get("/api/playbooks/{team}/{version}")
def get_playbook_version(team: str, version: int) -> dict:
    _check_team(team)
    if version < 0:
        raise HTTPException(status_code=400, detail="version must be a non-negative integer")
    team_dir = _versions_dir() / team
    version_dir = team_dir / f"v{version}"
    playbook = _read_obj(version_dir / "playbook.json")
    out = _fill(playbook, {"parent": None, "prompts": {}, "rules": [], "tools": [], "params": {}})
    out["version"] = version
    out["team"] = team
    out["prompts"] = _as_dict(out.get("prompts"))
    out["rules"] = _as_list(out.get("rules"))
    out["tools"] = _as_list(out.get("tools"))
    out["params"] = _as_dict(out.get("params"))
    out["tool_sources"] = _tool_sources(version_dir, out["tools"])
    out["tool_stats"] = {k: v for k, v in _read_obj(team_dir / "tool_stats.json").items() if isinstance(v, dict)}
    return out


# ------------------------------------------------------------------ events


def _read_events(path: Path, since: int) -> tuple[list[dict], int]:
    """Events with seq >= since, and the number of complete lines read.

    seq is the 0-based line index. An unparseable *last* line is treated as a write in
    progress: it is not returned and not counted, so the next poll picks it up once complete.
    Unparseable lines in the middle are skipped but still counted (they will never heal).
    """
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return [], 0
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # trailing newline: not a line
    events = []
    count = 0
    for idx, line in enumerate(lines):
        is_last = idx == len(lines) - 1
        record = None
        if line.strip():
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            if not isinstance(record, dict):
                record = None
                if is_last:
                    break  # partial write in progress
        count = idx + 1
        if record is not None and idx >= since:
            # the engine omits round/team on run-level events; the contract always has them (null)
            events.append({**EVENT_DEFAULTS, **record, "seq": idx})
    return events, count


@app.get("/api/events")
def get_events(since: int = Query(0)) -> dict:
    events, count = _read_events(_runs_dir() / "events.jsonl", max(0, since))
    if REPLAY:  # only what had happened by the replay clock; seq stays the file line index
        t = REPLAY.now()
        upto = next((e["seq"] for e in events if (_replay_mod._ts(e.get("ts")) or 0) > t), count)
        events = [e for e in events if e["seq"] < upto]
        count = max(since, upto)
    return {"events": events, "next": count}


# ------------------------------------------------------------------ built frontend (SPA)
# Registered last so every /api route above wins.


# ------------------------------------------------------------------ live view
_LIVE_LABELS = [
    (re.compile(r"^r(\d+)-builder-c(\d+)_val$"), lambda m: f"Round {m[1]} · gate · Builder candidate {int(m[2]) + 1}", "builder"),
    (re.compile(r"^builder_(\d+)_val$"), lambda m: f"Builder v{m[1]} · validation", "builder"),
    (re.compile(r"^bugpool_extra(\d+)$"), lambda m: "Setup · Builder v0 drafts for the bug pool", "builder"),
    (re.compile(r"^r(\d+)-breaker-c(\d+)_pool$"), lambda m: f"Round {m[1]} · gate · Breaker candidate {int(m[2]) + 1}", "breaker"),
    (re.compile(r"^breaker_(\d+)_pool$"), lambda m: f"Breaker v{m[1]} · frozen bug pool", "breaker"),
    (re.compile(r"^test_(.+)$"), lambda m: f"Final exam · {m[1].replace('_', ' ')}", "builder"),
    (re.compile(r"^drafts_d(\d+)$"), lambda m: f"Final exam · draft {int(m[1]) + 1}", "builder"),
    (re.compile(r"^match$"), None, "match"),
]


def _ports(pid: str) -> tuple[list[dict], str]:
    try:
        from engine.dataset import load_problems

        p = load_problems().get(pid)
        if p:
            return [x.to_dict() for x in p.ports], p.spec
    except Exception:
        pass
    return [], ""


def _bits(v: Any, w: int) -> str:
    try:
        return format(int(v), f"0{max(1, int(w))}b")
    except (TypeError, ValueError):
        return str(v)


def _live_item(pid: str, row: dict, kind: str, pool_code: dict) -> dict:
    ports, spec = _ports(pid)
    widths = {p["name"]: p["width"] for p in ports}
    item = {"problem_id": pid, "spec": spec[:600], "ports": ports, "code": None, "compiled": None, "attempts": None,
            "official": None, "attack": None, "tools": [], "error": None}
    if kind == "breaker":  # an attack on a frozen buggy design
        item["code"] = pool_code.get(row.get("id"))
        item["compiled"] = True
        item["attack"] = {"cycles": row.get("cycles"), "found_bug": bool(row.get("caught")),
                          "first_mismatch": row.get("first_mismatch"), "stimulus": None}
        item["official"] = {"passed": False, "kind": "known buggy design"}
        return item
    build = row.get("build") if kind == "match" else row
    item.update(code=(build or {}).get("code"), compiled=(build or {}).get("compiled"), attempts=(build or {}).get("attempts"),
                error=(build or {}).get("error"), tools=(build or {}).get("tool_reports") or [])
    # builder result rows use "passed"; final-exam draft rows use "official_pass"
    off = row.get("official") if kind == "match" else {"passed": row.get("passed", row.get("official_pass")), "kind": row.get("kind")}
    if isinstance(off, dict):
        item["official"] = {"passed": bool(off.get("passed")), "kind": off.get("kind")}
    a = row.get("attack") if kind == "match" else None
    if isinstance(a, dict):
        stim = a.get("stimulus") or []
        item["attack"] = {"cycles": a.get("stimulus_cycles"), "found_bug": bool(a.get("valid_bug")),
                          "first_mismatch": a.get("first_mismatch"),
                          "stimulus": [{k: _bits(v, widths.get(k, 1)) for k, v in c.items()} for c in stim[:8]]}
    return item


@app.get("/api/live")
def get_live(limit: int = Query(12, ge=1, le=40)) -> dict:
    """What the agents are working on right now, read from the engine's progress files (newest first)."""
    runs = _runs_dir()
    files = [*runs.glob("cache/*.json"), *runs.glob("final/test_*.json"), *runs.glob("final/drafts_d*.json"),
             *runs.glob("round_*/match.json")]
    files = [f for f in files if f.is_file()]
    if not files:
        return {"source": None, "label": None, "team": None, "updated_at": None, "items": []}
    newest = max(files, key=lambda f: f.stat().st_mtime)
    if REPLAY:
        src, _ = REPLAY.live_source()
        if src is None:
            return {"source": None, "label": None, "team": None, "updated_at": None, "items": []}
        newest = src
    stem = newest.stem
    label, kind = None, "builder"
    for rx, fn, k in _LIVE_LABELS:
        m = rx.match(stem)
        if m:
            kind = k
            label = fn(m) if fn else f"Round {newest.parent.name.split('_')[-1]} · training match"
            break
    data = _read_json(newest)
    if not isinstance(data, dict):
        return {"source": stem, "label": label, "team": kind, "updated_at": None, "items": []}
    rows = data.get("problems") if kind == "match" else list((data.get("results") or {}).items())
    pool = {e.get("id"): e.get("code") for e in (_read_json(runs / "bug_pool.json") or {}).get("entries", [])} if kind == "breaker" else {}
    items = []
    if kind == "match":
        for r in (rows or [])[-limit:]:
            if isinstance(r, dict):
                items.append(_live_item(r.get("problem_id", "?"), r, kind, pool))
    else:
        for key, r in (rows or [])[-limit:]:
            if isinstance(r, dict):
                items.append(_live_item(r.get("problem_id") or key.split("#")[0], r, kind, pool))
    items.reverse()  # newest first (rows are saved in completion order)
    if REPLAY:  # keep the feed moving through the recorded rows
        allrows = [r for r in (rows or []) if isinstance(r, dict)] if kind == "match" else \
            [(k, r) for k, r in (rows or []) if isinstance(r, dict)]
        picked = REPLAY.window(allrows, limit)
        items = [_live_item(r.get("problem_id", "?"), r, kind, pool) if kind == "match"
                 else _live_item(r[1].get("problem_id") or r[0].split("#")[0], r[1], kind, pool) for r in picked]
        return {"source": stem, "label": label, "team": "builder" if kind == "match" else kind,
                "updated_at": _replay_mod._iso(__import__("time").time()) if REPLAY.playing else None, "items": items}
    import datetime as _dt

    return {"source": stem, "label": label, "team": "builder" if kind == "match" else kind,
            "updated_at": _dt.datetime.fromtimestamp(newest.stat().st_mtime, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": items}


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    dist = _root_dir() / "web" / "dist"
    index = dist / "index.html"
    if not dist.is_dir():
        return JSONResponse({"detail": "Frontend not built. Run `npm run build` in web/."}, status_code=404)
    if full_path:
        candidate = dist / full_path
        if not _is_within(candidate, dist):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        if "." in full_path.rsplit("/", 1)[-1]:
            return JSONResponse({"detail": "Not Found"}, status_code=404)  # missing asset, not a route
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def choose_data_dirs() -> str:
    """Which run to show; see engine.store.select_run_dirs (real run if present, else mock)."""
    from engine.store import select_run_dirs

    global REPLAY
    name = os.environ.get("SHADOWBOX_REPLAY")
    if name:
        runs = Path(name) if os.path.isabs(name) else _root_dir() / name
        config.RUNS_DIR = runs
        config.VERSIONS_DIR = runs.parent / runs.name.replace("runs", "versions", 1)
        REPLAY = _replay_mod.from_env(_root_dir())
        return f"replay ({REPLAY.speed:g}x)"
    return select_run_dirs()


def main() -> None:
    import uvicorn

    host = os.environ.get("SHADOWBOX_HOST", "127.0.0.1")
    port = int(os.environ.get("SHADOWBOX_PORT", "8000"))
    which = choose_data_dirs()
    print(f"Shadowbox API: serving the {which} run from {config.RUNS_DIR} (set SHADOWBOX_DATA=real|mock to choose)")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
