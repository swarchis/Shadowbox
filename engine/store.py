"""Plain-file storage: atomic JSON writes, the event log, and the run state file (see docs/CONTRACT.md)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data) -> None:
    """Write via temp file + rename so readers never see a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return out


def runs_dir() -> Path:
    return Path(config.RUNS_DIR)


def versions_dir() -> Path:
    return Path(config.VERSIONS_DIR)


def select_run_dirs(prefer: str | None = None) -> str:
    """For readers (server, `status`): show the real run if one exists, else the mock run, regardless
    of whether this process has an API key. SHADOWBOX_DATA=real|mock forces one; explicit
    SHADOWBOX_RUNS_DIR / SHADOWBOX_VERSIONS_DIR always win. Returns 'real', 'mock' or 'explicit'."""
    if os.environ.get("SHADOWBOX_RUNS_DIR") or os.environ.get("SHADOWBOX_VERSIONS_DIR"):
        return "explicit"
    root = Path(config.ROOT)
    want = (prefer or os.environ.get("SHADOWBOX_DATA", "auto")).lower()
    has_real = (root / "runs" / "state.json").exists()
    has_mock = (root / "runs_mock" / "state.json").exists()
    use_mock = want == "mock" or (want == "auto" and not has_real and has_mock)
    suffix = "_mock" if use_mock else ""
    config.RUNS_DIR = root / f"runs{suffix}"
    config.VERSIONS_DIR = root / f"versions{suffix}"
    config.MOCK = use_mock
    return "mock" if use_mock else "real"


def ledger_path() -> Path:
    return Path(config.LEDGER_PATH) if config.LEDGER_PATH else runs_dir() / "ledger.jsonl"


def event(type_: str, message: str, **fields) -> None:
    """Append to events.jsonl (the UI's live feed) and echo to the console."""
    rec = {"ts": now_iso(), "type": type_, "message": message, **fields}
    append_jsonl(runs_dir() / "events.jsonl", rec)
    print(f"[{rec['ts']}] {type_}: {message}", flush=True)


_STATE_DEFAULTS = {
    "status": "idle",
    "phase": "setup",
    "round": 0,
    "step": None,
    "message": "",
    "started_at": None,
    "deadline_at": None,
    "spend_usd": 0.0,
    "llm_calls": 0,
    "human_interventions": 0,
    "builder_version": 0,
    "breaker_version": 0,
    "splits": {},
}


def update_state(**fields) -> dict:
    with _lock:
        path = runs_dir() / "state.json"
        state = {**_STATE_DEFAULTS, **(read_json(path, {}) or {})}
        state.update(fields)
        state["mode"] = "mock" if config.MOCK else "real"
        state["spend_cap_usd"] = config.SPEND_CAP_USD
        state["updated_at"] = now_iso()
        write_json(path, state)
        return state


def read_state() -> dict:
    return {**_STATE_DEFAULTS, **(read_json(runs_dir() / "state.json", {}) or {})}
