"""Fast engine tests: dataset, harness, stimulus, toolbox sandbox, coach/gatekeeper rules, LLM parsing, and a
mini mock self-play loop.

Every test runs against temp folders (RUNS_DIR / VERSIONS_DIR / SPLITS_PATH are monkeypatched to tmp_path), the
offline mock LLM, and zero mock latency, so nothing in runs_mock/, versions_mock/ or data/ is ever touched.

Tests that once documented engine bugs (found in review) now guard the fixes as regression tests.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    coach,
    config,
    dataset,
    gatekeeper,
    harness,
    llm,
    loop,
    mock_llm,
    playbook,
    store,
    tools_runner,
)

pytestmark = pytest.mark.skipif(
    not config.RAW_DATASET_DIR.exists() or not (config.IVERILOG_BIN / "iverilog").exists(),
    reason="VerilogEval dataset or Icarus Verilog not installed (see README)",
)

REAL_SPLITS = config.SPLITS_PATH


# ------------------------------------------------------------------ fixtures and helpers
@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own runs/versions folders and a private copy of the locked splits."""
    runs, versions = tmp_path / "runs", tmp_path / "versions"
    splits = tmp_path / "data" / "splits.json"
    if REAL_SPLITS.exists():
        splits.parent.mkdir(parents=True)
        shutil.copy(REAL_SPLITS, splits)
    monkeypatch.setattr(config, "RUNS_DIR", runs)
    monkeypatch.setattr(config, "VERSIONS_DIR", versions)
    monkeypatch.setattr(config, "SPLITS_PATH", splits)
    monkeypatch.setattr(config, "MOCK", True)
    monkeypatch.setattr(config, "SPEND_CAP_USD", 45.0)
    monkeypatch.setattr(mock_llm, "LATENCY_S", 0.0)
    yield {"runs": runs, "versions": versions}
    assert store.runs_dir() == runs and store.versions_dir() == versions


def prob(pid: str) -> dataset.Problem:
    return dataset.load_problems()[pid]


def as_top(p: dataset.Problem) -> str:
    """The reference renamed to TopModule: a known-correct candidate design."""
    return dataset.ref_source(p).replace("module RefModule", "module TopModule")


DFF8AR = "Prob047_dff8ar"  # clk, d[7:0], areset (async, active high), q[7:0]
ANDGATE = "Prob014_andgate"  # a, b -> out = a & b

DFF8AR_SRC = """module TopModule (
  input clk,
  input [7:0] d,
  input areset,
  output reg [7:0] q
);
  always @(posedge clk, posedge areset)
    if (areset) q <= 0;
    else q <= d;
endmodule
"""


# ================================================================== dataset.parse_ports
def test_parse_ports_sequential_reference():
    p = prob(DFF8AR)
    assert [(x.name, x.direction, x.width) for x in p.ports] == [
        ("clk", "input", 1), ("d", "input", 8), ("areset", "input", 1), ("q", "output", 8)]
    assert p.is_sequential and p.clock.name == "clk"
    assert [x.name for x in p.data_inputs] == ["d", "areset"]
    assert [x.name for x in p.outputs] == ["q"]


def test_parse_ports_nonzero_lsb_reference():
    ena = next(x for x in prob("Prob068_countbcd").ports if x.name == "ena")  # output [3:1] ena
    assert (ena.direction, ena.width, ena.msb, ena.lsb) == ("output", 3, 3, 1)
    assert ena.decl_range == "[3:1] "


def test_parse_ports_no_inputs_and_very_wide_references():
    zero = prob("Prob001_zero")
    assert [(x.name, x.direction, x.width) for x in zero.ports] == [("zero", "output", 1)]
    assert not zero.is_sequential and zero.data_inputs == []
    wide = {x.name: x.width for x in prob("Prob021_mux256to1v").ports}
    assert wide == {"in": 1024, "sel": 8, "out": 4}


def test_parse_ports_clock_named_clock_and_body_parameters():
    assert prob("Prob145_circuit8").clock.name == "clock"
    assert "clock" not in [x.name for x in prob("Prob145_circuit8").data_inputs]
    # Prob079 declares `parameter A=0, B=1, ...` in the body; it must not leak into the port list.
    assert [x.name for x in prob("Prob079_fsm3onehot").ports] == ["in", "state", "next_state", "out"]


def test_parse_ports_every_reference_is_sane():
    problems = dataset.load_problems()
    assert len(problems) == 156 - len(dataset.EXCLUDED)
    for p in problems.values():
        names = [x.name for x in p.ports]
        assert len(names) == len(set(names)), p.id
        assert p.outputs, p.id
        assert all(x.width >= 1 and x.direction in ("input", "output") for x in p.ports), p.id


def test_parse_ports_continuation_comments_and_types():
    src = """
    // module RefModule (input fake);
    module RefModule (
      input wire signed [3:0] a, b,   // b shares direction and range
      /* output [9:0] bogus, */
      input clk,
      output reg signed [7:0] y,
      output logic z,
      inout [1:0] io
    );
    endmodule
    """
    got = [(x.name, x.direction, x.width) for x in dataset.parse_ports(src)]
    assert got == [("a", "input", 4), ("b", "input", 4), ("clk", "input", 1), ("y", "output", 8),
                   ("z", "output", 1), ("io", "inout", 2)]


def test_parse_ports_picks_named_module_and_parameter_header():
    src = ("module helper(input x, output y); assign y = x; endmodule\n"
           "module TopModule #(parameter N = 4) (input [3:0] a, output [0:3] y);\nendmodule\n")
    ports = dataset.parse_ports(src, "TopModule")
    assert [(x.name, x.width) for x in ports] == [("a", 4), ("y", 4)]
    assert [x.name for x in dataset.parse_ports(src, "helper")] == ["x", "y"]


@pytest.mark.parametrize("src", [
    "module Other(input a); endmodule",  # no such module
    "module RefModule(a, b); input a; output b; endmodule",  # non-ANSI port list
])
def test_parse_ports_rejects_missing_or_non_ansi(src):
    with pytest.raises(ValueError):
        dataset.parse_ports(src)


# ================================================================== dataset splits
def _seq_frac(ids):
    probs = dataset.load_problems()
    return sum(probs[i].is_sequential for i in ids) / len(ids)


def test_split_sizes_disjoint_and_complete():
    s = dataset.make_splits()
    total = len(dataset.load_problems())
    assert (len(s["train"]), len(s["val"]), len(s["test"])) == (30, 30, total - 60)
    assert set(s["train"]).isdisjoint(s["val"]) and set(s["train"]).isdisjoint(s["test"]) and set(s["val"]).isdisjoint(s["test"])
    assert set(s["train"]) | set(s["val"]) | set(s["test"]) == set(dataset.load_problems())
    assert all(s[k] == sorted(s[k]) for k in s)
    assert not set(dataset.EXCLUDED) & set(s["train"] + s["val"] + s["test"])


def test_split_is_stratified_by_sequential():
    s = dataset.make_splits()
    overall = _seq_frac(list(dataset.load_problems()))
    for k in ("train", "val", "test"):
        assert abs(_seq_frac(s[k]) - overall) < 0.05, k


def test_split_determinism_and_custom_sizes():
    assert dataset.make_splits(1234) == dataset.make_splits(1234)
    other = dataset.make_splits(99)
    assert other != dataset.make_splits(1234)
    assert (len(other["train"]), len(other["val"])) == (30, 30)
    small = dataset.make_splits(1234, {"train": 10, "val": 6})
    assert (len(small["train"]), len(small["val"]), len(small["test"])) == (10, 6, len(dataset.load_problems()) - 16)


def test_locked_splits_match_seeded_generator_and_are_not_rewritten():
    locked = json.loads(config.SPLITS_PATH.read_text())
    assert locked["seed"] == config.SPLIT_SEED
    assert {k: locked[k] for k in ("train", "val", "test")} == dataset.make_splits()
    before = config.SPLITS_PATH.read_text()
    assert dataset.load_splits() == locked
    assert config.SPLITS_PATH.read_text() == before
    four = dataset.split_problems("train", limit=4)
    assert [p.id for p in four] == locked["train"][:4]


def test_load_splits_creates_file_when_missing(tmp_path, monkeypatch):
    path = tmp_path / "fresh" / "splits.json"
    monkeypatch.setattr(config, "SPLITS_PATH", path)
    with pytest.raises(FileNotFoundError):
        dataset.load_splits(create=False)
    s = dataset.load_splits()
    assert path.exists() and s["seed"] == config.SPLIT_SEED and len(s["train"]) == 30


# ================================================================== harness.run_official
def test_run_official_passes_reference():
    r = harness.run_official(prob(DFF8AR), as_top(prob(DFF8AR)))
    assert (r.passed, r.kind, r.mismatches) == (True, "pass", 0)
    assert r.samples and r.samples > 0


def test_run_official_fails_mutated_reference():
    mutant = as_top(prob(DFF8AR)).replace("q <= 0", "q <= 1")
    assert mutant != as_top(prob(DFF8AR))
    r = harness.run_official(prob(DFF8AR), mutant)
    assert not r.passed and r.kind == "mismatch" and r.mismatches > 0
    comb = harness.run_official(prob(ANDGATE), as_top(prob(ANDGATE)).replace("a & b", "a | b"))
    assert not comb.passed and comb.kind == "mismatch"


def test_run_official_syntax_error():
    r = harness.run_official(prob(ANDGATE), "module TopModule(input a, input b, output out);\n assign out = a &;\nendmodule\n")
    assert not r.passed and r.kind == "syntax"


def test_every_reference_passes_official_and_compile_check():
    def one(p):
        src = as_top(p)
        o, c = harness.run_official(p, src), harness.compile_check(p, src)
        return p.id, o.passed, o.kind, c.ok, c.errors

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(one, dataset.load_problems().values()))
    bad = [r for r in res if not (r[1] and r[3])]
    assert not bad, bad


def test_warning_mentioning_error_identifier_is_not_a_compile_failure():
    p = prob(DFF8AR)
    src = DFF8AR_SRC.replace("  always", "  assign next_error = d[0];  // implicit wire -> iverilog -Wall warning\n  always", 1)
    cc = harness.compile_check(p, src)
    assert cc.warnings  # the warning is real...
    assert cc.ok, cc.errors  # ...but it is not an error
    assert harness.run_official(p, src).passed


# ================================================================== harness.compile_check (interface)
def _cc_errors(src):
    return harness.compile_check(prob(DFF8AR), src)


def test_compile_check_clean_design():
    cc = _cc_errors(DFF8AR_SRC)
    assert cc.ok and cc.errors == [] and cc.feedback() == "Compiles cleanly."


@pytest.mark.parametrize("src,expected", [
    (DFF8AR_SRC.replace("TopModule", "top_module"), "no module named TopModule"),
    (DFF8AR_SRC.replace("  input areset,\n", ""), "missing port input areset"),
    (DFF8AR_SRC.replace("input [7:0] d", "output [7:0] d"), "port d should be input"),
    (DFF8AR_SRC.replace("input [7:0] d", "input [3:0] d"), "port d should be 8 bits wide, got 4"),
    (DFF8AR_SRC.replace("  input areset,\n", "  input areset,\n  input en,\n"), "unexpected extra port en"),
    ("module TopModule(clk, d, areset, q);\n input clk; input [7:0] d; input areset; output reg [7:0] q;\nendmodule\n",
     "could not parse TopModule port list"),
])
def test_compile_check_interface_mismatch_messages(src, expected):
    cc = _cc_errors(src)
    assert not cc.ok
    assert any(expected in e for e in cc.errors), cc.errors
    assert expected in cc.feedback()


def test_compile_check_reports_real_syntax_error():
    cc = _cc_errors(DFF8AR_SRC.replace("q <= d;", "q <= d"))
    assert not cc.ok and cc.errors and all(not e.startswith("missing port") for e in cc.errors)


@pytest.mark.parametrize("pid,src", [
    (DFF8AR, "module TopModule #(parameter W = 8) (input clk, input [W-1:0] d, input areset, output reg [W-1:0] q);\n"
             "  always @(posedge clk, posedge areset) if (areset) q <= 0; else q <= d;\nendmodule\n"),
    ("Prob031_dff", "module TopModule(input clk, input d, output reg q = 1'b0);\n  always @(posedge clk) q <= d;\nendmodule\n"),
    (DFF8AR, DFF8AR_SRC.replace("input [7:0] d", "input wire logic unsigned [7:0] d")),
])
def test_compile_check_accepts_valid_ansi_variants(pid, src):
    p = prob(pid)
    assert harness.run_official(p, src).passed  # the design really is correct
    cc = harness.compile_check(p, src)
    assert cc.ok, cc.errors


# ================================================================== harness.normalize_stimulus
def test_normalize_value_formats():
    p = prob(DFF8AR)
    cycles = [{"d": "0xff"}, {"d": "0XA"}, {"d": "0b101"}, {"d": "12"}, {"d": "8'hA5"}, {"d": "4'b1010"},
              {"d": "8'd200"}, {"d": "0b1010_0101"}, {"d": -1}, {"d": " 7 "}, {"d": 3, "areset": True}]
    out = harness.normalize_stimulus(p, {"cycles": cycles})
    assert [c["d"] for c in out] == [255, 10, 5, 12, 0xA5, 10, 200, 0xA5, 255, 7, 3]
    assert out[-1]["areset"] == 1


def test_normalize_holds_values_and_starts_at_zero():
    p = prob(DFF8AR)
    out = harness.normalize_stimulus(p, [{"d": 5}, {"areset": 1}, {}, {"d": 0, "areset": 0}])
    assert out == [{"d": 5, "areset": 0}, {"d": 5, "areset": 1}, {"d": 5, "areset": 1}, {"d": 0, "areset": 0}]
    assert harness.normalize_stimulus(p, {"cycles": [{"d": 5}]}) == harness.normalize_stimulus(p, [{"d": 5}])


def test_normalize_ignores_clock_and_truncates():
    p = prob(DFF8AR)
    assert harness.normalize_stimulus(p, [{"clk": 1, "d": 1}]) == [{"d": 1, "areset": 0}]
    long = harness.normalize_stimulus(p, [{"d": i % 256} for i in range(config.STIMULUS_MAX_CYCLES + 50)])
    assert len(long) == config.STIMULUS_MAX_CYCLES
    assert harness.normalize_stimulus(prob("Prob001_zero"), [{}]) == [{}]


@pytest.mark.parametrize("stim,msg", [
    ([{"bogus": 1}], "unknown input"),
    ([{"d": 256}], "does not fit"),
    ([{"d": "0x100"}], "does not fit"),
    ([{"areset": 2}], "does not fit"),
    ([{"d": "abc"}], "bad value"),
    ([{"d": "0x"}], "bad value"),
    ([{"d": "4'bxx01"}], "bad value"),
    ([{"d": 1.5}], "bad value"),
    ([{"d": None}], "bad value"),
    ([{"d": [1]}], "bad value"),
    ([], "at least one cycle"),
    ({}, "at least one cycle"),
    ({"cycles": []}, "at least one cycle"),
    ("0101", "at least one cycle"),
    ([{"d": 1}, 5], "not an object"),
])
def test_normalize_rejects_bad_stimulus(stim, msg):
    with pytest.raises(harness.StimulusError, match=msg):
        harness.normalize_stimulus(prob(DFF8AR), stim)


def test_random_stimulus_deterministic_in_range_and_resets_first():
    p = prob(DFF8AR)
    a, b = harness.random_stimulus(p, 50, seed=4), harness.random_stimulus(p, 50, seed=4)
    assert a == b and a != harness.random_stimulus(p, 50, seed=5)
    assert all(set(c) == {"d", "areset"} and 0 <= c["d"] < 256 and c["areset"] in (0, 1) for c in a)
    assert a[0]["areset"] == 1 and a[1]["areset"] == 1
    w = harness.random_stimulus(prob("Prob021_mux256to1v"), 5, seed=1)
    assert all(0 <= c["in"] < (1 << 1024) for c in w)


# ================================================================== harness.check_against_ref
def test_check_against_ref_no_false_positives_on_any_reference():
    def one(p):
        c = harness.check_against_ref(p, as_top(p), harness.random_stimulus(p, 40, seed=3))
        return p.id, c.valid_bug, c.error, c.total_samples

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(one, dataset.load_problems().values()))
    bad = [r for r in res if r[1] or r[2] or r[3] == 0]
    assert not bad, bad


def test_check_against_ref_catches_real_bug():
    p = prob(DFF8AR)
    mutant = DFF8AR_SRC.replace("q <= 0", "q <= 1")
    chk = harness.check_against_ref(p, mutant, {"cycles": [{"areset": 1, "d": "0x00"}, {"areset": 0, "d": 7}]})
    assert chk.valid_bug and chk.error is None and chk.mismatched_samples > 0
    fm = chk.first_mismatch
    assert fm["signal"] == "q" and fm["cycle"] == 0 and fm["expected"] == "00000000" and fm["got"] == "00000001"
    assert set(chk.to_dict(with_trace=True)["trace"]) == {"labels", "error", "errors", "samples"}


def test_check_against_ref_compile_failure_is_not_a_bug():
    chk = harness.check_against_ref(prob(DFF8AR), "module TopModule(input clk; endmodule", {"cycles": [{"d": 1}]})
    assert not chk.valid_bug and chk.error and chk.error.startswith("compile failed")


def test_check_against_ref_accepts_partial_bare_list():
    p = prob(DFF8AR)
    chk = harness.check_against_ref(p, as_top(p), [{"d": 3}, {"areset": 1}])
    assert not chk.valid_bug and chk.total_samples == 4


def test_comment_mentioning_module_does_not_break_simulation():
    p = prob(DFF8AR)
    src = "// Top module for an 8-bit register\n" + DFF8AR_SRC.replace(
        "else q <= d;", "else begin : copy\n      integer i;\n      for (i = 0; i < 8; i = i + 1) q[i] <= d[i];\n    end")
    assert harness.compile_check(p, src).ok and harness.run_official(p, src).passed
    chk = harness.check_against_ref(p, src, harness.random_stimulus(p, 20, seed=1))
    assert chk.error is None and chk.total_samples > 0 and not chk.valid_bug


# ================================================================== harness.group_by_behavior
def test_group_by_behavior_identical_vs_different():
    p = prob(ANDGATE)
    good = as_top(p)
    same = "module TopModule(input a, input b, output out);\n  assign out = ~(~a | ~b);  // De Morgan\nendmodule\n"
    bad = good.replace("a & b", "a | b")
    gr = harness.group_by_behavior(p, {"d0": good, "d1": bad, "d2": same}, harness.random_stimulus(p, 16, seed=2))
    assert gr.error is None
    assert gr.groups == [["d0", "d2"], ["d1"]]
    dis = gr.first_disagreement
    assert dis and set(dis["outputs"]) == {"d0", "d1", "d2"}
    assert dis["outputs"]["d0"] == dis["outputs"]["d2"] != dis["outputs"]["d1"]


def test_group_by_behavior_all_identical_sequential():
    p = prob(DFF8AR)
    gr = harness.group_by_behavior(p, {"a": as_top(p), "b": DFF8AR_SRC, "c": DFF8AR_SRC},
                                   {"cycles": [{"areset": 1}, {"areset": 0, "d": "0x5a"}, {"d": 3}]})
    assert gr.groups == [["a", "b", "c"]] and gr.first_disagreement is None and gr.error is None
    assert {s.phase for s in gr.trace.samples} == {"pre", "post"}


def test_group_by_behavior_largest_group_first_and_compile_failure():
    p = prob(ANDGATE)
    good, bad = as_top(p), as_top(p).replace("a & b", "a ^ b")
    gr = harness.group_by_behavior(p, {"x": bad, "y": good, "z": good}, harness.random_stimulus(p, 16, seed=2))
    assert gr.groups == [["y", "z"], ["x"]]
    broken = harness.group_by_behavior(p, {"x": good, "y": "module TopModule(; endmodule"}, [{"a": 1, "b": 1}])
    assert broken.groups == [["x"], ["y"]] and broken.error
    with pytest.raises(ValueError):
        harness.group_by_behavior(p, {"ref": good}, [{"a": 1}])


# ================================================================== tools_runner
GOOD_TOOL = '''import re


def run(spec, verilog, ports):
    found = [p["name"] for p in ports if p["direction"] == "input" and not re.search(r"\\b" + p["name"] + r"\\b", verilog.split(");", 1)[-1])]
    return {"fired": bool(found), "findings": ["unused input " + n for n in found]}
'''


def test_screen_accepts_reasonable_tools():
    assert tools_runner.screen_tool_code(GOOD_TOOL) == []
    for _, code in list(mock_llm.BUILDER_TOOLS.values()) + list(mock_llm.BREAKER_TOOLS.values()):
        assert tools_runner.screen_tool_code(code) == []


_RUN = "def run(spec, verilog, ports):\n    return {'fired': False, 'findings': []}\n"


@pytest.mark.parametrize("code,msg", [
    ("import os\n" + _RUN, "import of os not allowed"),
    ("from subprocess import run as r\n" + _RUN, "import from subprocess not allowed"),
    ("import socket, re\n" + _RUN, "import of socket not allowed"),
    (_RUN + "x = open('f', 'w')\n", "call to open() not allowed"),
    (_RUN + "eval('1')\n", "call to eval() not allowed"),
    (_RUN + "exec('1')\n", "call to exec() not allowed"),
    (_RUN + "__import__('os')\n", "call to __import__() not allowed"),
    (_RUN + "getattr(1, 'real')\n", "call to getattr() not allowed"),
    (_RUN + "y = os\n", "use of os not allowed"),
    (_RUN + "z = ().__class__\n", "attribute __class__ not allowed"),
    (_RUN + "PID = 'Prob031_dff'\n", "hardcodes a problem id"),
    ("def check(spec, verilog, ports):\n    return {}\n", "missing top-level `def run(spec, verilog, ports)`"),
    ("def run(spec, verilog):\n    return {}\n", "missing top-level `def run(spec, verilog, ports)`"),
    ("def run(spec, verilog, ports)\n    return {}\n", "syntax error"),
    (_RUN + "\n" * 200, "longer than"),
])
def test_screen_rejects_banned_code(code, msg):
    problems = tools_runner.screen_tool_code(code)
    assert any(msg in p for p in problems), problems


@pytest.mark.parametrize("code", [
    "import typing\n\ndef run(spec, verilog, ports):\n    return {'fired': True, 'findings': [typing.sys.platform]}\n",
    "import json\n\ndef run(spec, verilog, ports):\n    return {'fired': True, 'findings': [json.codecs.open('/etc/hosts').read()]}\n",
    "def run(spec, verilog, ports):\n    return {'fired': True, 'findings': [__builtins__['open']('/etc/hosts').read()]}\n",
])
def test_screen_blocks_indirect_module_and_file_access(code):
    assert tools_runner.screen_tool_code(code) != []


PORTS = [{"name": "a", "direction": "input", "width": 1}, {"name": "y", "direction": "output", "width": 1}]


def test_run_tool_returns_findings():
    out = tools_runner.run_tool(GOOD_TOOL, "spec", "module TopModule(input a, output y);\n assign y = 1;\nendmodule\n", PORTS)
    assert out == {"fired": True, "findings": ["unused input a"]}
    out = tools_runner.run_tool(GOOD_TOOL, "spec", "module TopModule(input a, output y);\n assign y = ~a;\nendmodule\n", PORTS)
    assert out == {"fired": False, "findings": []}


@pytest.mark.parametrize("code,msg", [
    ("def run(spec, verilog, ports):\n    return 5\n", "TypeError"),
    ("def run(spec, verilog, ports):\n    raise ValueError('boom')\n", "ValueError: boom"),
    ("syntax error here(\n", "SyntaxError"),
])
def test_run_tool_reports_errors(code, msg):
    out = tools_runner.run_tool(code, "s", "v", PORTS)
    assert out["fired"] is False and msg in out["error"]


def test_run_tool_timeout():
    out = tools_runner.run_tool("def run(spec, verilog, ports):\n    while True:\n        pass\n", "s", "v", PORTS, timeout=1)
    assert out == {"fired": False, "findings": [], "error": "tool timed out"}


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="sandbox-exec is macOS only")
def test_run_tool_blocks_writes_outside_its_temp_dir(tmp_path):
    target = tmp_path / "escaped.txt"
    code = (f"def run(spec, verilog, ports):\n    open({str(target)!r}, 'w').write('x')\n"
            "    return {'fired': True, 'findings': ['wrote it']}\n")
    out = tools_runner.run_tool(code, "s", "v", PORTS)
    assert not target.exists()
    assert out["fired"] is False and "Error" in out.get("error", "")
    inside = ("def run(spec, verilog, ports):\n    open('scratch.txt', 'w').write('ok')\n"
              "    return {'fired': True, 'findings': [open('scratch.txt').read()]}\n")
    assert tools_runner.run_tool(inside, "s", "v", PORTS) == {"fired": True, "findings": ["ok"]}


# ================================================================== coach.apply
EVIDENCE = ["Prob031_dff", "Prob035_count1to10", "Prob047_dff8ar", "Prob068_countbcd"]


def builder_pb(**kw) -> playbook.Playbook:
    pb = playbook.default_playbook("builder")
    for k, v in kw.items():
        setattr(pb, k, v)
    return pb


def test_apply_rule_add_and_clone_semantics():
    pb = builder_pb(rules=["Existing rule."])
    cand, err = coach.apply(pb, {"change_type": "rule_add", "rule": "  Use non-blocking assignments.  "}, [], "r1-builder-c0")
    assert err is None
    assert cand.rules == ["Existing rule.", "Use non-blocking assignments."]
    assert (cand.version, cand.parent, cand.team) == ("r1-builder-c0", 0, "builder")
    assert pb.rules == ["Existing rule."] and pb.version == 0  # original untouched


@pytest.mark.parametrize("prop,reason", [
    ({"change_type": "rule_add"}, "rule missing"),
    ({"change_type": "rule_add", "rule": "   "}, "rule missing"),
    ({"change_type": "rule_add", "rule": "x" * 401}, "too long"),
    ({"change_type": "rule_add", "rule": "Existing rule."}, "already present"),
    ({"change_type": "rule_remove", "rule_index": 5}, "bad rule_index"),
    ({"change_type": "rule_remove", "rule_index": -1}, "bad rule_index"),
    ({"change_type": "rule_remove", "rule_index": "0"}, "bad rule_index"),
    ({"change_type": "rule_remove"}, "bad rule_index"),
    ({"change_type": "prompt_edit", "role": "attacker", "prompt": "x" * 60}, "bad role"),
    ({"change_type": "prompt_edit", "role": "writer", "prompt": "too short"}, "prompt too short"),
    ({"change_type": "tool_remove", "tool_name": "nope"}, "no such tool"),
    ({"change_type": "param", "param": "temperature", "value": 1}, "unknown param"),
    ({"change_type": "param", "param": "max_cycles", "value": 50}, "unknown param"),  # breaker-only param
    ({"change_type": "param", "param": "max_debug_attempts", "value": 0}, "int in [1, 3]"),
    ({"change_type": "param", "param": "max_debug_attempts", "value": 4}, "int in [1, 3]"),
    ({"change_type": "param", "param": "max_debug_attempts", "value": True}, "int in [1, 3]"),
    ({"change_type": "param", "param": "max_debug_attempts", "value": "3"}, "int in [1, 3]"),
    ({"change_type": "param", "param": "max_debug_attempts", "value": 2}, "already has that value"),
    ({"change_type": "param", "param": "use_planner", "value": 1}, "true/false"),
    ({"change_type": "param", "param": "use_planner", "value": False}, "already has that value"),
    ({"change_type": "delete_everything"}, "unknown change_type"),
    ({}, "unknown change_type"),
])
def test_apply_invalid_builder_proposals(prop, reason):
    cand, err = coach.apply(builder_pb(rules=["Existing rule."]), prop, EVIDENCE, "c")
    assert cand is None and reason in err


def test_apply_rule_remove_prompt_edit_and_params():
    pb = builder_pb(rules=["r0", "r1", "r2"])
    cand, err = coach.apply(pb, {"change_type": "rule_remove", "rule_index": 1}, [], "c")
    assert err is None and cand.rules == ["r0", "r2"]
    text = "You are a careful hardware engineer. Always name the module TopModule and match the ports."
    cand, err = coach.apply(pb, {"change_type": "prompt_edit", "role": "writer", "prompt": text}, [], "c")
    assert err is None and cand.prompts["writer"] == text and cand.prompts["debugger"] == pb.prompts["debugger"]
    cand, err = coach.apply(pb, {"change_type": "param", "param": "max_debug_attempts", "value": 3}, [], "c")
    assert err is None and cand.params["max_debug_attempts"] == 3
    cand, err = coach.apply(pb, {"change_type": "param", "param": "use_planner", "value": True}, [], "c")
    assert err is None and cand.params["use_planner"] is True


def test_apply_breaker_prompt_and_param_rules():
    pb = playbook.default_playbook("breaker")
    keep = 'You are a verification engineer. Return {"cycles": [...]} JSON with at most {max_cycles} cycles.'
    cand, err = coach.apply(pb, {"change_type": "prompt_edit", "role": "attacker", "prompt": keep}, [], "c")
    assert err is None and cand.prompts["attacker"] == keep
    cand, err = coach.apply(pb, {"change_type": "prompt_edit", "role": "attacker", "prompt": "x" * 80}, [], "c")
    assert cand is None and "JSON stimulus format" in err
    cand, err = coach.apply(pb, {"change_type": "prompt_edit", "role": "writer", "prompt": keep}, [], "c")
    assert cand is None and "bad role" in err
    cand, err = coach.apply(pb, {"change_type": "param", "param": "max_cycles", "value": 60}, [], "c")
    assert err is None and cand.params["max_cycles"] == 60
    for bad in (7, 201):
        assert coach.apply(pb, {"change_type": "param", "param": "max_cycles", "value": bad}, [], "c")[0] is None
    assert "unknown param" in coach.apply(pb, {"change_type": "param", "param": "use_planner", "value": True}, [], "c")[1]


def _tool_prop(name="unused_inputs", code=GOOD_TOOL, evidence=EVIDENCE[:3]):
    return {"change_type": "tool_add", "tool_name": name, "tool_code": code, "evidence_problems": list(evidence)}


def test_apply_tool_add_and_remove():
    pb = builder_pb()
    cand, err = coach.apply(pb, _tool_prop(), EVIDENCE, "c")
    assert err is None and cand.tools == ["unused_inputs"] and cand.tool_sources["unused_inputs"] == GOOD_TOOL
    assert pb.tools == [] and pb.tool_sources == {}
    removed, err = coach.apply(cand, {"change_type": "tool_remove", "tool_name": "unused_inputs"}, [], "c2")
    assert err is None and removed.tools == [] and "unused_inputs" not in removed.tool_sources


@pytest.mark.parametrize("prop,pb_kw,reason", [
    (_tool_prop(name="bad-name"), {}, "Python identifier"),
    (_tool_prop(name="dup"), {"tools": ["dup"], "tool_sources": {"dup": GOOD_TOOL}}, "already in toolbox"),
    (_tool_prop(), {"tools": [f"t{i}" for i in range(config.TOOLBOX_CAP)],
                    "tool_sources": {f"t{i}": GOOD_TOOL for i in range(config.TOOLBOX_CAP)}}, "toolbox is full"),
    (_tool_prop(evidence=EVIDENCE[:2]), {}, "cited 2 valid"),
    (_tool_prop(evidence=["Prob001_zero", "Prob002_m2014_q4i", "Prob003_step_one"]), {}, "cited 0 valid"),  # not failing problems
    (_tool_prop(code="import os\n" + _RUN), {}, "static screen"),
    (_tool_prop(code="def run(spec, verilog, ports):\n    return ports[5]\n"), {}, "crashed on a smoke test"),
])
def test_apply_invalid_tool_add(prop, pb_kw, reason):
    cand, err = coach.apply(builder_pb(**pb_kw), prop, EVIDENCE, "c")
    assert cand is None and reason in err


@pytest.mark.parametrize("prop", [{"change_type": ["rule_add"]}, {"change_type": "param", "param": ["max_debug_attempts"], "value": 3}])
def test_apply_rejects_unhashable_fields(prop):
    cand, err = coach.apply(builder_pb(), prop, [], "c")
    assert cand is None and err


def test_apply_rule_add_null_rule_is_rejected():
    cand, err = coach.apply(builder_pb(), {"change_type": "rule_add", "rule": None}, [], "c")
    assert cand is None and "rule missing" in err


def test_apply_rule_remove_rejects_bool_index():
    cand, err = coach.apply(builder_pb(rules=["r0", "r1", "r2"]), {"change_type": "rule_remove", "rule_index": True}, [], "c")
    assert cand is None and "bad rule_index" in err


# ================================================================== gatekeeper
def _res(key, passing, all_ids):
    return {i: {key: i in passing} for i in all_ids}


def test_flips_and_score():
    ids = ["p1", "p2", "p3", "p4", "p5"]
    cur = _res("passed", {"p1", "p2"}, ids)
    cand = _res("passed", {"p2", "p3", "p4", "p5"}, ids)
    assert gatekeeper.flips(cur, cand, "passed") == (["p3", "p4", "p5"], ["p1"], 2)
    assert gatekeeper.flips(cur, cur, "passed") == ([], [], 0)
    assert gatekeeper.score(cand, "passed") == 0.8 and gatekeeper.score({}, "passed") == 0.0
    # paired comparison: only items evaluated on both sides count, and items that hit API errors are skipped
    assert gatekeeper.flips({}, {"x": {"caught": True}, "y": {"caught": False}}, "caught") == ([], [], 0)
    assert gatekeeper.flips({"x": {"caught": False, "error": "boom"}}, {"x": {"caught": True}}, "caught") == ([], [], 0)
    errored = {**cur, "p3": {"passed": False, "error": "api"}}
    assert gatekeeper.score(errored, "passed") == 0.5  # errored items leave the denominator
    assert gatekeeper.flips({"z": {"caught": True}}, {"x": {"caught": False}}, "caught") == ([], [], 0)


def _e(name, net, lost=0):
    gained = (net + lost) if net is not None else 0
    return {"id": name, "net_flips": net, "gained": ["g"] * max(0, gained), "lost": ["l"] * lost}


def test_decide_margin_and_tie_breaks():
    m = config.GATE_MARGIN
    assert gatekeeper.decide([]) is None
    assert gatekeeper.decide([_e("a", None)]) is None
    assert gatekeeper.decide([_e("a", m - 1, lost=1)]) is None  # below margin and not clean
    assert gatekeeper.decide([_e("a", 1)]) is None  # fixes only one
    assert gatekeeper.decide([_e("a", config.CLEAN_WIN_MIN)])["id"] == "a"  # clean win: fixes 2, breaks 0
    assert gatekeeper.decide([_e("a", m)])["id"] == "a"
    assert gatekeeper.decide([_e("a", m), _e("b", m + 2), _e("c", None)])["id"] == "b"
    assert gatekeeper.decide([_e("a", m, lost=2), _e("b", m, lost=0)])["id"] == "b"
    assert gatekeeper.decide([_e("a", -5), _e("b", m - 1, lost=1)]) is None


# ================================================================== llm output parsing
V1 = "module TopModule(input a, output y);\n  assign y = a;\nendmodule"
V2 = "module TopModule(input a, output y);\n  assign y = ~a;\nendmodule"


@pytest.mark.parametrize("text,expected", [
    (f"Draft:\n```verilog\n{V1}\n```\nOops, fixed:\n```verilog\n{V2}\n```\n", V2),  # last block wins
    (f"```systemverilog\n{V1}\n```", V1),
    (f"```sv\n{V1}\n```", V1),
    (f"```Verilog title=top.sv\n{V1}\n```", V1),
    (f"```\n{V1}\n```", V1),
    (f"```verilog\n{V1}\n```\nTest it with:\n```python\nprint('module x')\n```\n", V1),  # non-verilog block ignored
    (f"```json\n{{\"a\": 1}}\n```\n```verilog\n{V2}\n```", V2),
    (f"<answer>\n{V1}\n</answer>", V1),  # bare module, no fence
    (f"```verilog\n{V2}\n", V2),  # unclosed fence (truncated output)
])
def test_extract_code(text, expected):
    assert llm.extract_code(text) == expected + "\n"


def test_extract_code_none():
    assert llm.extract_code("I could not write this design.") is None
    assert llm.extract_code("```python\nprint(1)\n```") is None


def test_extract_code_bare_module_after_prose():
    assert llm.extract_code(f"Here is the module you asked for:\n{V1}\n") == V1 + "\n"


@pytest.mark.parametrize("text,expected", [
    ('```json\n{"cycles": [{"a": 1}]}\n```', {"cycles": [{"a": 1}]}),
    ('```json\n{"a": 1}\n```\nrevised:\n```json\n{"a": 2}\n```', {"a": 2}),  # last block wins
    ('```json\n{"a": 1}\n```\nrevised:\n```json\n{"a": 2,}\n```', {"a": 1}),  # invalid last block falls back
    ('```\n{"a": 3}\n```', {"a": 3}),
    ('Sure! The stimulus is {"cycles": [{"x": "0x1f"}]} as requested.', {"cycles": [{"x": "0x1f"}]}),
    ('Here: [{"a": 1}, {"a": 0}] done', [{"a": 1}, {"a": 0}]),
    ('{"proposals": [{"change_type": "rule_add", "rule": "Use {braces} carefully"}]}',
     {"proposals": [{"change_type": "rule_add", "rule": "Use {braces} carefully"}]}),
])
def test_extract_json(text, expected):
    assert llm.extract_json(text) == expected


@pytest.mark.parametrize("text", ["no json here", "```json\n{broken\n```", "", "{a} and [b"])
def test_extract_json_raises(text):
    with pytest.raises(ValueError):
        llm.extract_json(text)


def test_extract_json_after_verilog_block():
    text = ("The bug is in the shift:\n```verilog\nalways @(posedge clk) q[7:0] <= {d[6:0], d[7]};\n```\n"
            "Attack:\n```json\n{\"cycles\": [{\"d\": 1}, {\"d\": 2}]}\n```\n")
    assert llm.extract_json(text) == {"cycles": [{"d": 1}, {"d": 2}]}


def test_strip_reasoning():
    assert llm.strip_reasoning("<think>hmm</think>\nanswer") == ("answer", "<think>hmm</think>")
    text, thoughts = llm.strip_reasoning("<think>a</think>x <think>b</think> y")
    assert text == "x  y" and thoughts == "<think>a</think>\n<think>b</think>"
    text, thoughts = llm.strip_reasoning("reasoning without opener</think>\n```verilog\nmodule m; endmodule\n```")
    assert text.startswith("```verilog") and "reasoning without opener" in thoughts
    assert llm.strip_reasoning("  plain answer  ") == ("plain answer", None)
    assert llm.strip_reasoning("") == ("", None)
    assert llm.strip_reasoning(None) == ("", None)
    code_in_thoughts = "<think>```verilog\nmodule Bad; endmodule\n```</think>Final:\n```verilog\nmodule Good; endmodule\n```"
    assert "Good" in llm.extract_code(llm.strip_reasoning(code_in_thoughts)[0])


# ================================================================== store / playbook basics
def test_store_atomic_json_and_state(isolated):
    path = isolated["runs"] / "sub" / "x.json"
    store.write_json(path, {"a": 1})
    assert store.read_json(path) == {"a": 1} and not list(path.parent.glob(".x.json.*"))
    path.write_text("{half")
    assert store.read_json(path, "dflt") == "dflt"
    st = store.update_state(status="running")
    assert st["mode"] == "mock" and st["status"] == "running" and (isolated["runs"] / "state.json").exists()


def test_playbook_promote_and_fingerprint():
    playbook.ensure_v0()
    pb = playbook.load_current("builder")
    cand, _ = coach.apply(pb, _tool_prop(), EVIDENCE, "r1-builder-c0")
    assert cand.fingerprint() != pb.fingerprint()
    v = playbook.promote(cand, 1)
    assert v == 1 and playbook.current_version("builder") == 1
    back = playbook.load("builder", 1)
    assert back.tools == ["unused_inputs"] and back.tool_sources["unused_inputs"] == GOOD_TOOL
    assert back.fingerprint() == cand.fingerprint() and back.created_round == 1 and back.parent == 0


# ================================================================== mini mock loop
LOOP_KW = dict(rounds=1, minutes=None, k=1, train_limit=4, val_limit=4)


def _snapshot(runs: Path, versions: Path) -> dict[str, bytes]:
    files = {}
    for base in (runs, versions):
        for f in sorted(base.rglob("*")):
            if f.is_file() and f.name not in ("events.jsonl", "state.json", "series.json"):
                files[str(f.relative_to(base.parent))] = f.read_bytes()
    return files


def test_mini_mock_loop_completes_and_rerun_is_noop(isolated):
    runs, versions = isolated["runs"], isolated["versions"]
    ctx = asyncio.run(loop.run_loop(**LOOP_KW, llm=llm.LLMClient(mock=True)))
    assert len(ctx.train) == 4 and len(ctx.val) == 4

    r1 = runs / "round_1"
    for f in ("match.json", "builder_gate.json", "breaker_gate.json", "done.json"):
        assert (r1 / f).exists(), f
    assert (runs / "series.json").exists() and (versions / "lineage.json").exists()
    assert loop.completed_rounds() == [1]

    match = store.read_json(r1 / "match.json")
    assert match["round"] == 1 and len(match["problems"]) == 4
    assert set(match["summary"]) == {"train_pass", "hard_pass", "bugs_found", "subtle_bugs", "problems"}
    for row in match["problems"]:
        assert {"problem_id", "spec", "is_sequential", "official", "hard_pass", "build", "attack"} <= set(row)
        assert "log_tail" not in row["official"]
        assert {"code", "compiled", "attempts", "steps", "tool_reports"} <= set(row["build"])

    gate = store.read_json(r1 / "builder_gate.json")
    # k=1 coach proposal + 1 settings-sweep proposal (+ 1 memory proposal when the round had verified solutions)
    assert gate["complete"] is True and gate["team"] == "builder" and len(gate["entries"]) in (2, 3)
    assert [e["source"] for e in gate["entries"]][:2] == ["coach", "sweep"]

    series = store.read_json(runs / "series.json")
    assert [p["round"] for p in series["points"]] == [0, 1]
    lineage = store.read_json(versions / "lineage.json")["entries"]
    assert {"r1-breaker-c0", "r1-builder-c0", "r1-builder-c1"} <= {e["id"] for e in lineage}
    assert all(e["accepted"] == (e["new_version"] is not None) for e in lineage)
    assert store.read_state()["mode"] == "mock"

    ledger_rows = len(store.read_jsonl(runs / "ledger.jsonl"))
    assert ledger_rows > 0
    before = _snapshot(runs, versions)
    series_before = store.read_json(runs / "series.json")

    asyncio.run(loop.run_loop(**LOOP_KW, llm=llm.LLMClient(mock=True)))
    assert len(store.read_jsonl(runs / "ledger.jsonl")) == ledger_rows  # no new LLM calls
    assert _snapshot(runs, versions) == before  # no checkpoint rewritten or added
    assert store.read_json(runs / "series.json") == series_before
    assert loop.completed_rounds() == [1]
