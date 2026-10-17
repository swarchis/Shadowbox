"""Icarus Verilog harness: compile checks, official scoring, and stimulus-driven comparisons.

Two kinds of comparison share one testbench generator:
- vs reference (training only): Builder design vs RefModule. Any difference = a real bug.
- drafts vs drafts (test time): no reference; drafts are grouped by identical behavior.
"""
from __future__ import annotations

import random
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config
from .dataset import CLOCK_NAMES, Port, Problem, parse_ports, ref_source

RESET_NAMES = ("reset", "areset", "rst", "resetn", "aresetn", "rst_n")


class HarnessError(RuntimeError):
    pass


# ------------------------------------------------------------------ process helpers
def _bin(name: str) -> str:
    path = config.IVERILOG_BIN / name
    if not path.exists():
        raise HarnessError(f"{name} not found at {path}. Install Icarus Verilog (see README).")
    return str(path)


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, bool]:
    """Returns (returncode, combined output, timed_out)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return -1, out + "\nTIMEOUT", True


# iverilog reports problems as "file:line: error: ...", "file:line: syntax error", "N error(s) during
# elaboration" or "I give up". Matching those (not the bare word "error") avoids failing designs with
# signals like `next_error` that appear in warnings.
_ERR_RE = re.compile(r"(:\s*error\s*:|\bsyntax error\b|error\(s\) during|\bI give up\b|^\s*error\s*:)", re.I)


def is_error_line(line: str) -> bool:
    return bool(_ERR_RE.search(line))


# ------------------------------------------------------------------ source helpers
def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def declared_modules(src: str) -> list[str]:
    return re.findall(r"^\s*(?:extern\s+)?(?:macro)?module\s+(\w+)", _strip_comments(src), re.M)


def rename_modules(src: str, prefix: str) -> str:
    """Prefix every module declared in `src` (and its uses) so several designs can share one sim."""
    for name in sorted(set(declared_modules(src)), key=len, reverse=True):
        src = re.sub(rf"\b{re.escape(name)}\b", f"{prefix}{name}", src)
    return src


def interface_problems(problem: Problem, src: str) -> list[str]:
    """Check TopModule exists and its ports match the spec's interface."""
    if "TopModule" not in declared_modules(src):
        return ["no module named TopModule"]
    try:
        got = {p.name: p for p in parse_ports(src, "TopModule", lenient=True)}
    except ValueError as e:
        return [f"could not parse TopModule port list ({e}); use an ANSI-style port list"]
    msgs = []
    for want in problem.ports:
        p = got.get(want.name)
        if p is None:
            msgs.append(f"missing port {want.direction} {want.name}")
        elif p.direction != want.direction:
            msgs.append(f"port {want.name} should be {want.direction}")
        elif p.width > 0 and p.width != want.width:  # width -1 = not statically known; the compiler decides
            msgs.append(f"port {want.name} should be {want.width} bits wide, got {p.width}")
    for name in got:
        if name not in {w.name for w in problem.ports}:
            msgs.append(f"unexpected extra port {name}")
    return msgs


# ------------------------------------------------------------------ compile check
@dataclass
class CompileResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    log: str

    def feedback(self) -> str:
        if self.ok and not self.warnings:
            return "Compiles cleanly."
        lines = [*(f"ERROR: {e}" for e in self.errors), *(f"WARNING: {w}" for w in self.warnings)]
        return "\n".join(lines[:30])


def compile_check(problem: Problem, src: str) -> CompileResult:
    """Standalone compile of the candidate. Uses nothing from the reference or testbench."""
    iface = interface_problems(problem, src)
    with tempfile.TemporaryDirectory(prefix="sbx_cc_") as tmp:
        tmpd = Path(tmp)
        (tmpd / "top.sv").write_text(src)
        top = ["-s", "TopModule"] if "TopModule" in declared_modules(src) else []
        rc, log, timed_out = _run(
            [_bin("iverilog"), *config.IVERILOG_FLAGS, *top, "-o", "a.out", "top.sv"], tmpd, config.COMPILE_TIMEOUT_S
        )
    log = log.replace(str(tmpd) + "/", "")
    errors = [l.strip() for l in log.splitlines() if is_error_line(l)]
    warnings = [l.strip() for l in log.splitlines() if "warning" in l.lower()]
    if timed_out:
        errors.append("compiler timed out")
    if rc != 0 and not errors:
        errors.append(log.strip()[-400:] or f"iverilog exited with code {rc}")
    errors = iface + errors
    return CompileResult(ok=not errors, errors=errors, warnings=warnings, log=log[-4000:])


# ------------------------------------------------------------------ official scoring
@dataclass
class OfficialResult:
    passed: bool
    kind: str  # pass | syntax | compile | bind | timeout | mismatch | no_result
    mismatches: int | None
    samples: int | None
    hints: list[str]
    log_tail: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_official(problem: Problem, src: str) -> OfficialResult:
    """Grade with VerilogEval's own testbench, using the same flags and pass rule as its Makefile/analyzer.

    The result is for scoring and coaches only. It encodes reference behavior, so it must never be
    fed back to a Builder agent while that agent is still working on the problem.
    """
    with tempfile.TemporaryDirectory(prefix="sbx_off_") as tmp:
        tmpd = Path(tmp)
        (tmpd / "top.sv").write_text(src)
        rc, clog, c_to = _run(
            [_bin("iverilog"), *config.IVERILOG_FLAGS, "-s", "tb", "-o", "sim", "top.sv", problem.test_path, problem.ref_path],
            tmpd,
            config.COMPILE_TIMEOUT_S,
        )
        clog = clog.replace(str(tmpd) + "/", "")
        if "syntax error" in clog:
            return OfficialResult(False, "syntax", None, None, [], clog[-2000:])
        if "Unable to bind" in clog:
            return OfficialResult(False, "bind", None, None, [], clog[-2000:])
        if c_to or rc != 0 or any(is_error_line(l) for l in clog.splitlines()):
            return OfficialResult(False, "compile", None, None, [], clog[-2000:])
        rc, slog, s_to = _run([_bin("vvp"), "-n", "sim"], tmpd, config.SIM_TIMEOUT_S)
    hints = [l.strip() for l in slog.splitlines() if l.startswith("Hint:")]
    if s_to or "TIMEOUT" in slog:
        return OfficialResult(False, "timeout", None, None, hints, slog[-2000:])
    m = re.search(r"^Mismatches: (\d+) in (\d+) samples$", slog, re.M)
    if not m:
        return OfficialResult(False, "no_result", None, None, hints, slog[-2000:])
    mism, samples = int(m.group(1)), int(m.group(2))
    return OfficialResult(mism == 0, "pass" if mism == 0 else "mismatch", mism, samples, hints, slog[-2000:])


# ------------------------------------------------------------------ stimulus
class StimulusError(ValueError):
    pass


def _parse_value(v, width: int, name: str) -> int:
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, int):
        val = v
    elif isinstance(v, str):
        s = v.strip().lower().replace("_", "")
        try:
            if re.fullmatch(r"\d*'s?[bhd][0-9a-f]+", s):
                body = s.split("'")[1].lstrip("s")
                val = int(body[1:], {"b": 2, "h": 16, "d": 10}[body[0]])
            elif s.startswith("0x"):
                val = int(s, 16)
            elif s.startswith("0b"):
                val = int(s, 2)
            else:
                val = int(s, 10)
        except ValueError:
            raise StimulusError(f"bad value {v!r} for input {name}")
    else:
        raise StimulusError(f"bad value {v!r} for input {name}")
    if val < 0:
        val &= (1 << width) - 1  # allow -1 style all-ones
    if val >= (1 << width):
        raise StimulusError(f"value {v!r} does not fit in {width}-bit input {name}")
    return val


def normalize_stimulus(problem: Problem, stimulus) -> list[dict[str, int]]:
    """Validate a Breaker stimulus. Accepts {"cycles": [...]} or a bare list of per-cycle dicts.
    Inputs missing from a cycle hold their previous value (start at 0)."""
    cycles = stimulus.get("cycles") if isinstance(stimulus, dict) else stimulus
    if not isinstance(cycles, list) or not cycles:
        raise StimulusError('stimulus must be {"cycles": [ {input: value, ...}, ... ]} with at least one cycle')
    widths = {p.name: p.width for p in problem.data_inputs}
    state = {n: 0 for n in widths}
    out = []
    for i, cyc in enumerate(cycles[: config.STIMULUS_MAX_CYCLES]):
        if not isinstance(cyc, dict):
            raise StimulusError(f"cycle {i} is not an object")
        for k, v in cyc.items():
            if k in CLOCK_NAMES:
                continue  # the harness drives the clock
            if k not in widths:
                raise StimulusError(f"cycle {i}: unknown input {k!r}; valid inputs: {sorted(widths)}")
            state[k] = _parse_value(v, widths[k], k)
        out.append(dict(state))
    return out


def random_stimulus(problem: Problem, n_cycles: int = config.RANDOM_STIMULUS_CYCLES, seed: int = 0) -> list[dict[str, int]]:
    """Uniform random inputs; reset-like inputs are asserted for the first cycles, then pulsed rarely."""
    rng = random.Random(seed)
    cycles = []
    for i in range(n_cycles):
        cyc = {}
        for p in problem.data_inputs:
            if p.name in RESET_NAMES:
                active = 0 if p.name.endswith("n") else 1
                assert_now = i < 2 or rng.random() < 0.05
                cyc[p.name] = active if assert_now else 1 - active
            else:
                cyc[p.name] = rng.getrandbits(p.width)
        cycles.append(cyc)
    return cycles


# ------------------------------------------------------------------ comparison testbench
@dataclass
class Sample:
    cycle: int
    phase: str  # "pre" (inputs settled, before clock edge) | "post" (after rising edge) | "comb"
    inputs: dict[str, int]
    outputs: dict[str, dict[str, str]]  # design label -> output name -> binary string (may contain x/z)


@dataclass
class Trace:
    labels: list[str]
    samples: list[Sample] = field(default_factory=list)
    error: str | None = None  # first error, for display
    errors: dict[str, str] = field(default_factory=dict)  # label -> why that design produced no/partial output

    def to_dict(self, max_samples: int = 400) -> dict:
        return {
            "labels": self.labels,
            "error": self.error,
            "errors": self.errors,
            "samples": [asdict(s) for s in self.samples[:max_samples]],
        }


def _tb_source(problem: Problem, module: str, cycles: list[dict[str, int]]) -> str:
    """Testbench driving ONE design; every design is simulated in its own process with the same tb,
    so designs can't interfere (module names, `default_nettype, file-scope declarations)."""
    seq = problem.is_sequential
    clk = problem.clock.name if seq else None
    L = ["`resetall", "`timescale 1 ps/1 ps", "module sbx_tb;"]
    if seq:
        L.append(f"  reg {clk} = 0;")
    for p in problem.data_inputs:
        L.append(f"  reg {p.decl_range}{p.name} = 0;")
    for o in problem.outputs:
        L.append(f"  wire {o.decl_range}sbx_out_{o.name};")
    conns = [f".{p.name}({p.name})" for p in problem.inputs] + [f".{o.name}(sbx_out_{o.name})" for o in problem.outputs]
    L.append(f"  {module} u_dut ({', '.join(conns)});")
    fmt = " ".join("%b" for _ in problem.outputs)
    args = ", ".join(f"sbx_out_{o.name}" for o in problem.outputs)

    def dump(i: int, phase: str) -> str:
        return f'    $display("S {i} {phase} {fmt}", {args});'

    L.append("  initial begin")
    for i, cyc in enumerate(cycles):
        for p in problem.data_inputs:
            L.append(f"    {p.name} = {p.width}'h{cyc[p.name]:x};")
        if seq:
            L += ["    #2;", dump(i, "pre"), f"    #3 {clk} = 1;", "    #2;", dump(i, "post"), f"    #3 {clk} = 0;"]
        else:
            L += ["    #5;", dump(i, "comb"), "    #5;"]
    L += ['    $display("SBX_DONE");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def _simulate_one(problem: Problem, src: str, module: str, cycles: list[dict[str, int]]) -> tuple[dict, str | None]:
    """Returns ({(cycle, phase): {output: bits}}, error)."""
    with tempfile.TemporaryDirectory(prefix="sbx_sim_") as tmp:
        tmpd = Path(tmp)
        (tmpd / "design.sv").write_text("`resetall\n" + src + "\n`resetall\n")
        (tmpd / "tb.sv").write_text(_tb_source(problem, module, cycles))
        rc, clog, c_to = _run([_bin("iverilog"), *config.IVERILOG_FLAGS, "-s", "sbx_tb", "-o", "sim", "tb.sv", "design.sv"],
                              tmpd, config.COMPILE_TIMEOUT_S)
        if c_to or rc != 0:
            return {}, "compile failed: " + clog.replace(str(tmpd) + "/", "")[-1500:]
        rc, slog, s_to = _run([_bin("vvp"), "-n", "sim"], tmpd, config.SIM_TIMEOUT_S)
    out = {}
    for line in slog.splitlines():
        if not line.startswith("S "):
            continue
        parts = line.split()
        if len(parts) != 3 + len(problem.outputs):
            continue
        out[(int(parts[1]), parts[2])] = {o.name: v for o, v in zip(problem.outputs, parts[3:])}
    if s_to:
        return out, "simulation timed out (possible combinational loop)"
    if "SBX_DONE" not in slog:
        return out, "simulation ended early: " + slog[-500:]
    return out, None


def simulate(problem: Problem, designs: dict[str, str], cycles, include_ref: bool) -> Trace:
    """Drive every design (and optionally the reference, labelled 'ref') with the same stimulus."""
    cycles = normalize_stimulus(problem, cycles)
    jobs = []
    if include_ref:
        jobs.append(("ref", ref_source(problem), "RefModule"))
    for lab, src in designs.items():
        if not re.fullmatch(r"[A-Za-z]\w*", lab) or lab == "ref":
            raise ValueError(f"bad design label {lab!r}")
        jobs.append((lab, src, "TopModule"))
    trace = Trace(labels=[j[0] for j in jobs])
    per_label = {}
    for lab, src, module in jobs:
        res, err = _simulate_one(problem, src, module, cycles)
        per_label[lab] = res
        if err:
            trace.errors[lab] = err
            trace.error = trace.error or f"{lab}: {err}"
    phases = ("pre", "post") if problem.is_sequential else ("comb",)
    for i in range(len(cycles)):
        for ph in phases:
            outs = {lab: per_label[lab][(i, ph)] for lab in trace.labels if (i, ph) in per_label[lab]}
            if outs:
                trace.samples.append(Sample(i, ph, cycles[i], outs))
    return trace


def _ref_matches(ref_bits: str, dut_bits: str) -> bool:
    """Official rule: an X/Z bit in the reference matches anything; elsewhere bits must be identical."""
    if len(ref_bits) != len(dut_bits):
        return False
    return all(r in "xz" or r == d for r, d in zip(ref_bits.lower(), dut_bits.lower()))


@dataclass
class BugCheck:
    valid_bug: bool
    error: str | None
    first_mismatch: dict | None  # {cycle, phase, inputs, signal, expected, got}
    mismatched_samples: int
    total_samples: int
    trace: Trace | None = None

    def to_dict(self, with_trace: bool = False) -> dict:
        d = {k: v for k, v in asdict(self).items() if k != "trace"}
        if with_trace and self.trace:
            d["trace"] = self.trace.to_dict()
        return d


def check_against_ref(problem: Problem, design_src: str, stimulus) -> BugCheck:
    """TRAINING ONLY: does this stimulus expose a real bug in the design? Uses the reference oracle.
    Only samples where both the reference and the design produced output are compared, so a design
    that fails to simulate is reported as an error, never as a bug."""
    trace = simulate(problem, {"dut": design_src}, stimulus, include_ref=True)
    if "ref" in trace.errors:
        return BugCheck(False, "reference failed: " + trace.errors["ref"], None, 0, 0, trace)
    first, bad, total = None, 0, 0
    for s in trace.samples:
        if "ref" not in s.outputs or "dut" not in s.outputs:
            continue
        total += 1
        ref, dut = s.outputs["ref"], s.outputs["dut"]
        sample_bad = False
        for o in problem.outputs:
            if not _ref_matches(ref.get(o.name, ""), dut.get(o.name, "")):
                sample_bad = True
                if first is None:
                    first = {"cycle": s.cycle, "phase": s.phase, "inputs": s.inputs, "signal": o.name,
                             "expected": ref.get(o.name), "got": dut.get(o.name)}
        bad += sample_bad
    return BugCheck(bad > 0, trace.errors.get("dut"), first, bad, total, trace)


@dataclass
class GroupResult:
    groups: list[list[str]]  # design labels with identical behavior, largest group first
    first_disagreement: dict | None  # {cycle, phase, inputs, outputs: {label: {...}}}
    error: str | None
    trace: Trace | None = None


def _masked(values: list[str]) -> list[str]:
    """Blank a bit position only when NO draft has a known value there (all x/z, e.g. before reset).
    Where some drafts are known and others are X, the X is kept as its own symbol: a draft stuck at X
    behaves differently from drafts that drive 0/1, and must not hide their disagreements."""
    if not values or len({len(v) for v in values}) != 1:
        return values
    width = len(values[0])
    all_unknown = [all(v[i] in "xz" for v in values) for i in range(width)]
    return ["".join("-" if all_unknown[i] else v[i] for i in range(width)) for v in values]


def group_by_behavior(problem: Problem, drafts: dict[str, str], stimulus) -> GroupResult:
    """TEST TIME: no reference. Simulate drafts and group those with identical outputs.
    A draft that fails to simulate forms its own group."""
    trace = simulate(problem, drafts, stimulus, include_ref=False)
    ok = [lab for lab in drafts if lab not in trace.errors]
    failed = [lab for lab in drafts if lab in trace.errors]
    sig: dict[str, list] = {lab: [] for lab in ok}
    first = None
    for s in trace.samples:
        if not all(lab in s.outputs for lab in ok):
            continue
        per_out = {o.name: _masked([s.outputs[lab][o.name].lower() for lab in ok]) for o in problem.outputs}
        vals = {lab: tuple(per_out[o.name][k] for o in problem.outputs) for k, lab in enumerate(ok)}
        if first is None and len(set(vals.values())) > 1:
            first = {"cycle": s.cycle, "phase": s.phase, "inputs": s.inputs, "outputs": {k: dict(s.outputs[k]) for k in ok}}
        for lab in ok:
            sig[lab].append(vals[lab])
    buckets: dict[tuple, list[str]] = {}
    for lab in ok:
        buckets.setdefault(tuple(sig[lab]), []).append(lab)

    def unknown_bits(g):  # members of a group share a signature, so count once
        return sum(ch in "xz" for vals in sig[g[0]] for v in vals for ch in v)

    # largest group first; on equal size, the group with fewer unknown (X/Z) output bits first
    groups = sorted(buckets.values(), key=lambda g: (-len(g), unknown_bits(g), g[0])) + [[lab] for lab in failed]
    return GroupResult(groups, first, trace.error, trace)
