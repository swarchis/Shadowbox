"""API tests: every endpoint in docs/CONTRACT.md, against temp folders (never the real runs/)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from engine import config  # noqa: E402
from server.api import app  # noqa: E402


# ------------------------------------------------------------------ fixtures and helpers


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    root = tmp_path / "root"
    runs = tmp_path / "runs"
    versions = tmp_path / "versions"
    for d in (root, runs, versions):
        d.mkdir()
    monkeypatch.setattr(config, "ROOT", root)
    monkeypatch.setattr(config, "RUNS_DIR", runs)
    monkeypatch.setattr(config, "VERSIONS_DIR", versions)
    monkeypatch.setattr(config, "SPLITS_PATH", root / "data" / "splits.json")
    monkeypatch.setattr(config, "MOCK", True)
    monkeypatch.setattr(config, "SPEND_CAP_USD", 45.0)
    return {"root": root, "runs": runs, "versions": versions}


@pytest.fixture
def client(dirs):
    return TestClient(app)


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


MATCH = {
    "round": 1, "builder_version": 0, "breaker_version": 0,
    "summary": {"train_pass": 0.40, "hard_pass": 0.37, "bugs_found": 9, "subtle_bugs": 1, "problems": 30},
    "problems": [{
        "problem_id": "Prob031_dff",
        "spec": "I would like you to implement ...",
        "is_sequential": True,
        "official": {"passed": False, "kind": "mismatch", "mismatches": 12, "samples": 200},
        "hard_pass": False,
        "build": {"code": "module TopModule(...)...", "compiled": True, "attempts": 2,
                  "steps": [{"agent": "writer", "summary": "Wrote first draft"}],
                  "tool_reports": [{"tool": "lint_check", "fired": True, "findings": ["blocking"]}]},
        "attack": {"stimulus_cycles": 24, "valid_bug": True, "caught_by_official": True,
                   "first_mismatch": {"cycle": 3, "phase": "post", "signal": "q", "expected": "1", "got": "0",
                                      "inputs": {"d": 1}}},
    }],
}

PLAYBOOK_V2 = {
    "version": 2, "parent": 1, "team": "builder", "prompts": {"writer": "Write Verilog."},
    "rules": ["Use non-blocking assignments", "Name the module TopModule"], "tools": ["lint_check"],
    "params": {"max_debug_attempts": 2}, "created_round": 2,
}


# ------------------------------------------------------------------ empty state


def test_state_defaults_when_missing(client):
    body = client.get("/api/state").json()
    assert body["mode"] == "mock"
    assert body["status"] == "idle"
    assert body["phase"] == "setup"
    assert body["round"] == 0
    assert body["step"] is None
    assert body["spend_usd"] == 0
    assert body["spend_cap_usd"] == 45.0
    assert body["llm_calls"] == 0
    assert body["human_interventions"] == 0
    assert body["builder_version"] == 0
    assert body["breaker_version"] == 0
    assert body["deadline_at"] is None
    assert body["splits"] == {"train": 0, "val": 0, "test": 0}


def test_state_mode_real_when_not_mock(client, monkeypatch):
    monkeypatch.setattr(config, "MOCK", False)
    assert client.get("/api/state").json()["mode"] == "real"


def test_state_partial_file_fills_missing_keys(client, dirs):
    write(dirs["runs"] / "state.json", {"status": "running", "phase": "round", "round": 3, "spend_usd": None})
    write(dirs["root"] / "data" / "splits.json", {"seed": 1, "train": ["a", "b"], "val": ["c"], "test": ["d", "e", "f"]})
    body = client.get("/api/state").json()
    assert body["status"] == "running"
    assert body["round"] == 3
    assert body["spend_usd"] == 0
    assert body["builder_version"] == 0
    assert body["splits"] == {"train": 2, "val": 1, "test": 3}


def test_state_full_file_passes_through(client, dirs):
    state = {
        "mode": "real", "status": "running", "phase": "round", "round": 3, "step": "builder_gate",
        "message": "Gating", "started_at": "2026-10-16T22:00:00Z", "updated_at": "2026-10-16T22:31:05Z",
        "deadline_at": "2026-10-16T23:00:00Z", "spend_usd": 12.41, "spend_cap_usd": 45.0, "llm_calls": 812,
        "human_interventions": 0, "builder_version": 2, "breaker_version": 1,
        "splits": {"train": 30, "val": 30, "test": 92},
    }
    write(dirs["runs"] / "state.json", state)
    assert client.get("/api/state").json() == state


def test_state_corrupt_file_is_treated_as_missing(client, dirs):
    write(dirs["runs"] / "state.json", '{"status": "runn')
    body = client.get("/api/state").json()
    assert body["status"] == "idle"


@pytest.mark.parametrize("url, expected", [
    ("/api/series", {"points": [], "changes": []}),
    ("/api/lineage", {"entries": []}),
    ("/api/rounds", {"rounds": []}),
    ("/api/selection-examples", {"examples": []}),
    ("/api/demo-cases", {"cases": []}),
    ("/api/events", {"events": [], "next": 0}),
    ("/api/playbooks/builder", {"team": "builder", "current": 0, "versions": []}),
])
def test_empty_shapes(client, url, expected):
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == expected
    assert res.headers["cache-control"] == "no-store"


def test_empty_final(client):
    body = client.get("/api/final").json()
    assert body["complete"] is False
    assert body["notes"] == []
    assert body["metrics"]["v0"] is None and body["metrics"]["transfer_vbest"] is None


def test_empty_round_match(client):
    body = client.get("/api/rounds/4/match").json()
    assert body["round"] == 4
    assert body["problems"] == []
    assert body["summary"] == {"train_pass": None, "hard_pass": None, "bugs_found": None, "subtle_bugs": None,
                               "problems": None}


def test_empty_playbook_version(client):
    body = client.get("/api/playbooks/breaker/3").json()
    assert body == {"version": 3, "parent": None, "team": "breaker", "prompts": {}, "rules": [], "tools": [],
                    "params": {}, "tool_sources": {}, "tool_stats": {}}


def test_demo_config_defaults(client):
    body = client.get("/api/demo-config").json()
    assert body["project"] == "Shadowbox"
    assert body["tagline"] == "AI teams that get better by fighting themselves"
    assert body["team"] == []
    assert body["repo_url"] is None


# ------------------------------------------------------------------ file-backed endpoints


def test_series(client, dirs):
    series = {
        "points": [
            {"round": 0, "builder_val_pass": 0.43, "breaker_pool_catch": 0.52, "builder_train_pass": 0.40,
             "builder_hard_pass": 0.37, "builder_version": 0, "breaker_version": 0},
            {"round": 1, "builder_val_pass": 0.50, "breaker_pool_catch": 0.52, "builder_train_pass": 0.47,
             "builder_hard_pass": 0.43, "builder_version": 1, "breaker_version": 0},
        ],
        "changes": [{"round": 1, "team": "builder", "accepted": True, "summary": "NBA", "net_flips": 4}],
    }
    write(dirs["runs"] / "series.json", series)
    assert client.get("/api/series").json() == series


def test_lineage(client, dirs):
    entry = {
        "id": "r1-builder-c0", "round": 1, "team": "builder", "change_type": "rule_add",
        "summary": "Use non-blocking assignments", "reasoning": "5 of 14 ...", "evidence_problems": ["Prob031_dff"],
        "score_before": 0.43, "score_after": 0.53, "gained": ["Prob034_dff8"], "lost": [], "net_flips": 4,
        "accepted": True, "from_version": 0, "new_version": 1, "tool_name": None, "cost_usd": 0.92,
        "ts": "2026-10-16T22:14:00Z",
    }
    write(dirs["versions"] / "lineage.json", {"entries": [entry]})
    assert client.get("/api/lineage").json() == {"entries": [entry]}


def test_final(client, dirs):
    final = {
        "complete": True, "test_problems": 92,
        "metrics": {"v0": {"label": "Version 0", "pass": 0.41, "ci": [0.31, 0.51], "n": 92},
                    "vbest": {"label": "Latest version", "pass": 0.55, "ci": [0.45, 0.65], "n": 92}},
        "builder_versions": {"v0": 0, "vbest": 4}, "breaker_versions": {"v0": 0, "vbest": 3},
        "cost_usd": 9.80, "notes": ["CIs are 95% bootstrap over problems."],
    }
    write(dirs["runs"] / "final" / "final.json", final)
    body = client.get("/api/final").json()
    assert body["complete"] is True
    assert body["test_problems"] == 92
    assert body["metrics"]["vbest"]["pass"] == 0.55
    assert body["metrics"]["ultra"] is None  # missing metrics are null so the UI hides the bar
    assert body["builder_versions"] == {"v0": 0, "vbest": 4}
    assert body["cost_usd"] == 9.80


def test_final_fills_every_contract_metric_and_version_pair(client, dirs):
    write(dirs["runs"] / "final" / "final.json", {"complete": False, "metrics": {"v0": {"label": "Version 0", "pass": 0.4,
                                                                                    "ci": None, "n": 92},
                                                                             "ultra": "oops"},
                                                   "builder_versions": {"v0": 0}})
    body = client.get("/api/final").json()
    assert set(body["metrics"]) >= {"ablation_nano_coach", "ablation_main_coach", "vbest_selection"}
    assert body["metrics"]["ablation_main_coach"] is None
    assert body["metrics"]["ultra"] is None  # malformed metric is treated as missing
    assert body["builder_versions"] == {"v0": 0, "vbest": None}
    assert body["breaker_versions"] == {"v0": None, "vbest": None}


def test_empty_final_has_null_version_pairs(client):
    body = client.get("/api/final").json()
    assert body["builder_versions"] == {"v0": None, "vbest": None}
    assert body["metrics"]["ablation_main_coach"] is None
    assert body["test_problems"] is None and body["cost_usd"] is None


def test_selection_examples(client, dirs):
    examples = {"examples": [{
        "problem_id": "Prob112_always_case2", "spec": "...",
        "drafts": [{"label": "d0", "code": "...", "compiled": True, "official_pass": True},
                   {"label": "d1", "code": "...", "compiled": True, "official_pass": False}],
        "groups": [["d0"], ["d1"]], "chosen_group": 0, "chosen_label": "d0", "chosen_correct": True,
        "decided_by": "judge", "judge_reasoning": "d0 matches the spec",
        "disputed": {"cycle": 2, "phase": "comb", "inputs": {"in": 5},
                     "outputs": {"d0": {"pos": "010"}, "d1": {"pos": "000"}}},
        "stimulus_cycles": 18,
    }]}
    write(dirs["runs"] / "final" / "selection_examples.json", examples)
    assert client.get("/api/selection-examples").json() == examples


def test_demo_cases(client, dirs):
    cases = {"cases": [{
        "problem_id": "Prob047_dff8ar", "spec": "...",
        "v0": {"version": 0, "code": "...", "official_pass": False},
        "vbest": {"version": 4, "code": "...", "official_pass": True},
        "explanation": {"round": 2, "summary": "Handle async reset", "reasoning": "..."},
        "trace": {"signals": [{"name": "clk", "kind": "clock"}, {"name": "q", "kind": "output", "width": 8}],
                  "rows": [{"t": 0, "inputs": {"areset": "1"}, "expected": {"q": "00000000"},
                            "v0": {"q": "xxxxxxxx"}, "vbest": {"q": "00000000"}}],
                  "first_mismatch_row": 0},
    }]}
    write(dirs["runs"] / "final" / "demo_cases.json", cases)
    assert client.get("/api/demo-cases").json() == cases


def test_demo_config(client, dirs):
    cfg = {"project": "Shadowbox", "tagline": "AI teams that get better by fighting themselves",
           "team": [{"name": "Ada", "photo": None}, {"name": "Grace", "photo": "grace.jpg"}],
           "repo_url": "https://github.com/your-org/shadowbox"}
    write(dirs["root"] / "demo.json", cfg)
    assert client.get("/api/demo-config").json() == cfg


def test_non_object_list_items_are_dropped(client, dirs):
    write(dirs["runs"] / "series.json", {"points": [{"round": 0}, 3, "x"], "changes": [None]})
    write(dirs["runs"] / "final" / "demo_cases.json", {"cases": ["bad", {"problem_id": "p"}]})
    write(dirs["runs"] / "final" / "selection_examples.json", {"examples": [1, {"problem_id": "p"}]})
    write(dirs["versions"] / "lineage.json", {"entries": [[], {"id": "a"}]})
    assert client.get("/api/series").json() == {"points": [{"round": 0}], "changes": []}
    assert client.get("/api/demo-cases").json() == {"cases": [{"problem_id": "p"}]}
    assert client.get("/api/selection-examples").json() == {"examples": [{"problem_id": "p"}]}
    assert client.get("/api/lineage").json() == {"entries": [{"id": "a"}]}


def test_demo_config_team_members_are_normalized(client, dirs):
    write(dirs["root"] / "demo.json", {"team": [{"name": "Ada"}, {"name": 7, "photo": 3}, "Grace"]})
    assert client.get("/api/demo-config").json()["team"] == [{"name": "Ada", "photo": None}, {"name": "7", "photo": None}]


def test_wrong_top_level_types_fall_back_to_empty(client, dirs):
    write(dirs["runs"] / "series.json", [1, 2, 3])
    write(dirs["versions"] / "lineage.json", {"entries": "oops"})
    assert client.get("/api/series").json() == {"points": [], "changes": []}
    assert client.get("/api/lineage").json() == {"entries": []}


# ------------------------------------------------------------------ rounds


def test_rounds_scanning(client, dirs):
    runs = dirs["runs"]
    for n in (10, 2, 1):
        m = {**MATCH, "round": n, "builder_version": n - 1,
             "summary": {**MATCH["summary"], "train_pass": n / 100}}
        write(runs / f"round_{n}" / "match.json", m)
    write(runs / "round_1" / "done.json", {"ts": "x"})
    write(runs / "round_2" / "done.json", {"ts": "x"})
    (runs / "round_11").mkdir()  # in progress: no match.json yet
    write(runs / "round_abc" / "match.json", MATCH)  # ignored: not a number
    write(runs / "round_7", "a file, not a dir")  # ignored: not a dir
    (runs / "baseline").mkdir()

    rounds = client.get("/api/rounds").json()["rounds"]
    assert [r["round"] for r in rounds] == [1, 2, 10, 11]  # numeric, not lexical
    assert [r["complete"] for r in rounds] == [True, True, False, False]
    assert rounds[0] == {"round": 1, "complete": True, "builder_version": 0, "breaker_version": 0,
                         "train_pass": 0.01, "hard_pass": 0.37, "bugs_found": 9, "subtle_bugs": 1, "problems": 30}
    assert rounds[3]["train_pass"] is None and rounds[3]["builder_version"] is None


def test_rounds_problem_count_falls_back_to_problem_list(client, dirs):
    write(dirs["runs"] / "round_1" / "match.json", {**MATCH, "summary": {"train_pass": 0.5}})
    assert client.get("/api/rounds").json()["rounds"][0]["problems"] == 1


def test_round_match(client, dirs):
    write(dirs["runs"] / "round_1" / "match.json", MATCH)
    assert client.get("/api/rounds/1/match").json() == MATCH


def test_round_match_rejects_non_int(client):
    assert client.get("/api/rounds/abc/match").status_code == 422


# ------------------------------------------------------------------ playbooks


@pytest.fixture
def builder_versions(dirs):
    team = dirs["versions"] / "builder"
    write(team / "v0" / "playbook.json", {"version": 0, "parent": None, "team": "builder", "prompts": {},
                                          "rules": [], "tools": [], "params": {}, "created_round": None})
    write(team / "v1" / "playbook.json", {"version": 1, "parent": 0, "team": "builder", "rules": ["r"],
                                          "tools": [], "created_round": 1})
    write(team / "v2" / "playbook.json", PLAYBOOK_V2)
    write(team / "v2" / "tools" / "lint_check.py", "def run(spec, verilog, ports):\n    return []\n")
    write(team / "v10" / "playbook.json", '{"version": 10, "rul')  # partial write
    write(team / "current.json", {"version": 2})
    write(team / "tool_stats.json", {"lint_check": {"runs": 60, "fired": 14, "born_round": 2}})
    return team


def test_playbooks_list(client, builder_versions):
    body = client.get("/api/playbooks/builder").json()
    assert body["team"] == "builder"
    assert body["current"] == 2
    assert [v["version"] for v in body["versions"]] == [0, 1, 2, 10]
    assert body["versions"][0] == {"version": 0, "parent": None, "rules": 0, "tools": 0, "created_round": None}
    assert body["versions"][2] == {"version": 2, "parent": 1, "rules": 2, "tools": 1, "created_round": 2}
    assert body["versions"][3]["rules"] == 0  # unreadable playbook -> empty counts, not a 500


def test_playbooks_current_falls_back_to_latest(client, builder_versions):
    (builder_versions / "current.json").unlink()
    assert client.get("/api/playbooks/builder").json()["current"] == 10


def test_playbook_version_with_tool_sources(client, builder_versions):
    body = client.get("/api/playbooks/builder/2").json()
    assert body["version"] == 2
    assert body["parent"] == 1
    assert body["team"] == "builder"
    assert body["prompts"] == {"writer": "Write Verilog."}
    assert body["rules"] == PLAYBOOK_V2["rules"]
    assert body["tools"] == ["lint_check"]
    assert body["params"] == {"max_debug_attempts": 2}
    assert body["tool_sources"] == {"lint_check": "def run(spec, verilog, ports):\n    return []\n"}
    assert body["tool_stats"] == {"lint_check": {"runs": 60, "fired": 14, "born_round": 2}}


def test_playbook_version_without_tool_stats(client, builder_versions):
    (builder_versions / "tool_stats.json").unlink()
    body = client.get("/api/playbooks/builder/2").json()
    assert body["tool_stats"] == {}
    assert "lint_check" in body["tool_sources"]


def test_playbook_missing_tool_file_is_skipped(client, builder_versions):
    (builder_versions / "v2" / "tools" / "lint_check.py").unlink()
    body = client.get("/api/playbooks/builder/2").json()
    assert body["tools"] == ["lint_check"]
    assert body["tool_sources"] == {}


def test_breaker_playbooks_are_separate(client, builder_versions, dirs):
    write(dirs["versions"] / "breaker" / "v0" / "playbook.json", {"version": 0, "parent": None, "rules": ["x"]})
    body = client.get("/api/playbooks/breaker").json()
    assert body["team"] == "breaker"
    assert [v["version"] for v in body["versions"]] == [0]
    assert body["current"] == 0


# ------------------------------------------------------------------ path traversal


def test_invalid_team_rejected(client, builder_versions):
    assert client.get("/api/playbooks/coach").status_code == 400
    assert client.get("/api/playbooks/coach/0").status_code == 400
    assert client.get("/api/playbooks/%2E%2E").status_code == 400
    assert client.get("/api/playbooks/%2E%2E/0").status_code == 400


def test_non_int_version_rejected(client, builder_versions):
    assert client.get("/api/playbooks/builder/abc").status_code == 422
    assert client.get("/api/playbooks/builder/v2").status_code == 422
    assert client.get("/api/playbooks/builder/-1").status_code == 400


@pytest.mark.parametrize("url", [
    "/api/playbooks/..%2F..%2Fsecret/0",
    "/api/playbooks/builder/..%2F..%2Fsecret",
    "/api/rounds/..%2F..%2Fsecret/match",
])
def test_encoded_slash_traversal_does_not_leak(client, dirs, url):
    write(dirs["root"].parent / "secret" / "playbook.json", {"secret": "TOPSECRET"})
    res = client.get(url)
    assert res.status_code in (400, 404, 422)
    assert "TOPSECRET" not in res.text


def test_tool_names_cannot_escape_tools_dir(client, dirs):
    team = dirs["versions"] / "builder"
    write(dirs["versions"] / "evil.py", "TOPSECRET")
    write(team / "v0" / "playbook.json", {"version": 0, "tools": ["../../evil", "/etc/passwd", "ok_tool", 5]})
    write(team / "v0" / "tools" / "ok_tool.py", "def run(): pass\n")
    body = client.get("/api/playbooks/builder/0").json()
    assert body["tool_sources"] == {"ok_tool": "def run(): pass\n"}
    assert "TOPSECRET" not in json.dumps(body)


# ------------------------------------------------------------------ events


def _events_file(dirs, records, tail=""):
    lines = "".join(json.dumps(r) + "\n" for r in records)
    return write(dirs["runs"] / "events.jsonl", lines + tail)


def test_events_since_and_next(client, dirs):
    recs = [{"ts": f"t{i}", "type": "round_start", "round": i, "message": f"m{i}"} for i in range(5)]
    _events_file(dirs, recs)
    body = client.get("/api/events").json()
    assert [e["seq"] for e in body["events"]] == [0, 1, 2, 3, 4]
    assert body["events"][2] == {**recs[2], "team": None, "seq": 2}  # missing contract keys are null
    assert body["next"] == 5

    body = client.get("/api/events?since=3").json()
    assert [e["seq"] for e in body["events"]] == [3, 4]
    assert body["next"] == 5

    body = client.get("/api/events?since=5").json()
    assert body == {"events": [], "next": 5}


def test_events_corrupt_last_line_is_ignored_and_reread(client, dirs):
    recs = [{"ts": "t", "type": "gate_result", "message": "Accepted: +4 net"} for _ in range(3)]
    path = _events_file(dirs, recs, tail='{"ts": "t", "type": "gate_res')
    body = client.get("/api/events?since=0").json()
    assert [e["seq"] for e in body["events"]] == [0, 1, 2]
    assert body["next"] == 3  # partial line not counted, so the next poll reads it again

    # the engine finishes writing the line
    path.write_text(path.read_text() + 'ult", "message": "done"}\n')
    body = client.get(f"/api/events?since={body['next']}").json()
    assert body["events"] == [{"ts": "t", "type": "gate_result", "round": None, "team": None, "message": "done", "seq": 3}]
    assert body["next"] == 4


def test_events_corrupt_middle_line_is_skipped_but_counted(client, dirs):
    content = json.dumps({"type": "a"}) + "\n" + "garbage{\n" + "\n" + json.dumps({"type": "b"}) + "\n"
    write(dirs["runs"] / "events.jsonl", content)
    body = client.get("/api/events").json()
    assert [(e["seq"], e["type"]) for e in body["events"]] == [(0, "a"), (3, "b")]
    assert body["next"] == 4


def test_events_last_line_without_newline_but_complete(client, dirs):
    write(dirs["runs"] / "events.jsonl", json.dumps({"type": "a"}) + "\n" + json.dumps({"type": "b"}))
    body = client.get("/api/events").json()
    assert [e["type"] for e in body["events"]] == ["a", "b"]
    assert body["next"] == 2


def test_events_fill_missing_contract_keys(client, dirs):
    _events_file(dirs, [{"type": "run_start", "message": "go"}, {"ts": "t", "type": "gate_result", "round": 2,
                                                                  "team": "builder", "message": "ok", "accepted": True}])
    events = client.get("/api/events").json()["events"]
    assert events[0] == {"seq": 0, "ts": None, "type": "run_start", "round": None, "team": None, "message": "go"}
    assert events[1]["round"] == 2 and events[1]["team"] == "builder" and events[1]["accepted"] is True


def test_events_negative_since_is_zero(client, dirs):
    _events_file(dirs, [{"type": "a"}])
    assert client.get("/api/events?since=-4").json()["next"] == 1
    assert client.get("/api/events?since=abc").status_code == 422


# ------------------------------------------------------------------ frontend + CORS


def test_cors_allows_any_origin(client):
    res = client.get("/api/state", headers={"Origin": "http://localhost:5173"})
    assert res.headers["access-control-allow-origin"] == "*"


def test_no_frontend_build(client):
    res = client.get("/")
    assert res.status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404


def test_frontend_served_with_spa_fallback(client, dirs):
    dist = dirs["root"] / "web" / "dist"
    write(dist / "index.html", "<html>SHADOWBOX</html>")
    write(dist / "assets" / "app.js", "console.log('hi')")
    write(dirs["root"] / "web" / "secret.txt", "TOPSECRET")

    assert "SHADOWBOX" in client.get("/").text
    assert client.get("/assets/app.js").text == "console.log('hi')"
    assert "SHADOWBOX" in client.get("/evolution").text  # client-side route
    assert "SHADOWBOX" in client.get("/demo/scene/2").text
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/nope").status_code == 404  # API 404s never become index.html
    assert client.get("/api/state").json()["status"] == "idle"  # API routes win over the catch-all

    res = client.get("/..%2Fsecret.txt")
    assert "TOPSECRET" not in res.text
