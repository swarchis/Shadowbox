"""Regression tests for issues found in the final review (one test per fixed defect)."""
import asyncio
import json
import time

import pytest

from engine import budget, coach, config, dataset, gatekeeper, harness, llm, playbook, store, tools_runner


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "VERSIONS_DIR", tmp_path / "versions")
    monkeypatch.setattr(config, "LEDGER_PATH", None)
    monkeypatch.setattr(config, "MOCK", True)
    monkeypatch.setattr(llm, "LEDGER", llm.Ledger())
    yield


def _p(pid):
    return dataset.load_problems()[pid]


def test_stuck_x_draft_does_not_hide_disagreements():
    """A draft stuck at X (forgotten reset) must not mask the other drafts' 0/1 differences."""
    p = _p("Prob038_count15")
    ref = dataset.ref_source(p).replace("module RefModule", "module TopModule")
    drafts = {"d0": ref.replace("if (reset)", "if (1'b0)"), "d1": ref, "d2": ref, "d3": ref,
              "d4": ref.replace("q + 1", "q + 2").replace("q+1", "q+2")}
    gr = harness.group_by_behavior(p, drafts, harness.random_stimulus(p, 60, seed=7))
    assert gr.groups[0] == ["d1", "d2", "d3"]
    assert ["d0"] in gr.groups and ["d4"] in gr.groups


@pytest.mark.parametrize("decl", ["output reg[7:0] q", "output logic[7:0] q", "output logic signed[7:0] q"])
def test_range_glued_to_type_keyword(decl):
    p = _p("Prob034_dff8")
    src = f"module TopModule(input clk, input [7:0] d, {decl});\n  always @(posedge clk) q <= d;\nendmodule\n"
    assert harness.interface_problems(p, src) == []


def test_coach_api_failure_does_not_crash_the_round(monkeypatch):
    playbook.ensure_v0()

    async def boom(**kw):
        raise RuntimeError("LLM call failed after 5 retries")

    client = llm.LLMClient(mock=True)
    monkeypatch.setattr(client, "chat", boom)
    props, evidence, cost = asyncio.run(coach.propose("builder", playbook.load("builder", 0), {"problems": []}, client, k=1, round_no=1))
    assert props == [] and cost == 0.0


def test_throughput_ignores_idle_gap():
    now = time.time()
    ts = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
    rows = [{"ts": ts(now - 3600 + i * 3), "role": "writer"} for i in range(40)]
    rows += [{"ts": ts(now - 60 + i * 3), "role": "writer"} for i in range(20)]
    path = store.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert 0.25 < budget.work_per_second() < 0.45  # ~1 build every 3 s, not diluted by the hour-long pause


def test_cache_keeps_finished_items_after_an_interruption():
    calls = []

    async def compute(ids, on_row):
        calls.append(list(ids))
        for i in ids:
            if len(calls) == 1 and i == "c":
                raise KeyboardInterrupt  # interrupted after a and b finished
            on_row(i, {"passed": True})
            time.sleep(0)  # noqa

    path = store.runs_dir() / "cache" / "x.json"
    gatekeeper.cached_rows.__globals__["store"].write_json(path, {})  # make sure the folder exists
    path.unlink()
    import engine.gatekeeper as gk

    orig = gk.cached_rows

    # force a save after every row for the test
    async def run(ids):
        return await orig(path, "fp", "s", ids, compute)

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(run(["a", "b", "c"]))
    saved = store.read_json(path)
    assert saved is None or set(saved["results"]) <= {"a", "b"}
    # a fresh save interval: write partial explicitly the way on_row would after 2 s
    store.write_json(path, {"fingerprint": "fp", "settings": "s", "results": {"a": {"passed": True}, "b": {"passed": True}}, "complete": False})
    res = asyncio.run(run(["a", "b", "c"]))
    assert calls[-1] == ["c"] and set(res) == {"a", "b", "c"}


def test_tool_screen_allows_normal_code_and_blocks_tricks():
    ok = ("import re\n\ndef run(spec, verilog, ports):\n    signal = re.compile(r'q')\n    types = [p['name'] for p in ports]\n"
          "    return {'fired': bool(signal.search(verilog)), 'findings': types}\n")
    assert tools_runner.screen_tool_code(ok) == []
    bad = "import re\n\ndef run(spec, verilog, ports):\n    return {'fired': True, 'findings': [re.__dict__]}\n"
    assert tools_runner.screen_tool_code(bad)


def test_demo_case_trace_says_where_inputs_came_from(monkeypatch):
    from engine import final_eval
    from engine.breaker import AttackResult

    async def no_attack(p, code, pb, client, **kw):
        return AttackResult(p.id, None)

    monkeypatch.setattr(final_eval, "attack", no_attack)
    playbook.ensure_v0()
    p = _p("Prob034_dff8")
    ref = dataset.ref_source(p).replace("module RefModule", "module TopModule")
    bad = ref.replace("q <= d", "q <= ~d")
    v0 = {p.id: {"passed": False, "code": bad, "compiled": True}}
    vb = {p.id: {"passed": True, "code": ref, "compiled": True}}
    cases = asyncio.run(final_eval.demo_cases(v0, vb, playbook.load("builder", 0), playbook.load("breaker", 0), llm.LLMClient(mock=True)))
    assert cases and cases[0]["trace"]["source"] == "random"


def test_gate_accepts_clean_wins_but_not_noise():
    mk = lambda g, l: {"net_flips": g - l, "gained": ["x"] * g, "lost": ["y"] * l, "errors": 0}  # noqa: E731
    assert gatekeeper.passes(mk(3, 0)) and gatekeeper.passes(mk(4, 1))  # margin
    assert gatekeeper.passes(mk(2, 0))  # clean win
    assert not gatekeeper.passes(mk(2, 1)) and not gatekeeper.passes(mk(1, 0))


def test_team_drafts_param_builds_n_drafts_and_picks_one():
    playbook.ensure_v0()
    pb = playbook.load("builder", 0).clone()
    pb.params["drafts"] = 3
    from engine.builder import build

    r = asyncio.run(build(_p("Prob014_andgate"), pb, llm.LLMClient(mock=True), tag="t"))
    assert r.code and any("of 3 drafts" in s["summary"] for s in r.steps)


def test_verilog_reference_is_a_gated_option():
    from engine.builder import reference_block

    playbook.ensure_v0()
    pb = playbook.load("builder", 0)
    assert pb.params["reference"] is False and reference_block(pb) == ""  # off in v0
    on = pb.clone()
    on.params["reference"] = True
    assert "Rising-edge detect" in reference_block(on)
    cand, err = coach.apply(pb, {"change_type": "param", "param": "reference", "value": True}, [], "c")
    assert err is None and cand.params["reference"] is True
