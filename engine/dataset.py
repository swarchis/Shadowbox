"""VerilogEval v2 spec-to-RTL problems and the three locked splits."""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import config

CLOCK_NAMES = ("clk", "clock")

# Problems whose own reference fails the official grading, so nothing can pass them.
# Verified by running every reference through its testbench (tests/test_harness.py).
EXCLUDED = {
    "Prob082_lfsr32": "testbench hits its 1,000,000 ps limit and prints TIMEOUT, which the official analyzer fails",
    "Prob141_count_clock": "testbench hits its 1,000,000 ps limit and prints TIMEOUT, which the official analyzer fails",
    "Prob156_review2015_fancytimer": "testbench hits its 1,000,000 ps limit and prints TIMEOUT, which the official analyzer fails",
    "Prob099_m2014_q6c": "testbench connects ports Y2/Y4 that the reference module does not declare",
}


@dataclass(frozen=True)
class Port:
    name: str
    direction: str  # "input" | "output"
    width: int
    msb: int = 0
    lsb: int = 0

    @property
    def decl_range(self) -> str:
        return f"[{self.msb}:{self.lsb}] " if self.width > 1 or self.msb != 0 else ""

    def to_dict(self) -> dict:
        return {"name": self.name, "direction": self.direction, "width": self.width}


@dataclass(frozen=True)
class Problem:
    id: str
    spec: str  # the only thing agents may read
    ports: tuple[Port, ...]
    ref_path: str = field(repr=False)  # harness only
    test_path: str = field(repr=False)  # harness only

    @property
    def inputs(self) -> list[Port]:
        return [p for p in self.ports if p.direction == "input"]

    @property
    def outputs(self) -> list[Port]:
        return [p for p in self.ports if p.direction == "output"]

    @property
    def clock(self) -> Port | None:
        return next((p for p in self.inputs if p.name in CLOCK_NAMES), None)

    @property
    def is_sequential(self) -> bool:
        return self.clock is not None

    @property
    def data_inputs(self) -> list[Port]:
        """Inputs a stimulus controls (everything except the clock)."""
        return [p for p in self.inputs if p.name not in CLOCK_NAMES]

    def ports_summary(self) -> str:
        lines = []
        for p in self.ports:
            w = f"[{p.msb}:{p.lsb}]" if p.width > 1 else "1 bit"
            lines.append(f"{p.direction:6} {p.name} ({w})")
        return "\n".join(lines)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


_TYPE_WORDS = {"wire", "reg", "logic", "signed", "unsigned", "var", "tri", "bit"}


def _split_top(text: str) -> list[str]:
    """Split on commas that are not inside (), [] or {}."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _eval_int(expr: str, params: dict[str, int]) -> int | None:
    """Evaluate a constant width expression like `W-1` or `2*N` using known parameters."""
    import ast

    expr = re.sub(r"\b\d+'[sS]?[dD](\d+)", r"\1", expr.strip())
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.Name) and n.id in params:
            return params[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div)):
            l, r = ev(n.left), ev(n.right)
            return {ast.Add: l + r, ast.Sub: l - r, ast.Mult: l * r}.get(type(n.op), l // r if r else 0)
        raise ValueError
    try:
        return int(ev(tree))
    except (ValueError, TypeError, ZeroDivisionError, RecursionError):
        return None


def _params(header_params: str | None, body: str) -> dict[str, int]:
    out: dict[str, int] = {}
    text = (header_params or "") + ";" + body
    for m in re.finditer(r"\b(?:parameter|localparam)\b(?:\s+(?:integer|int|logic|bit|signed|unsigned))*(?:\s*\[[^\]]*\])?\s+([^;]*)", text):
        for assign in _split_top(m.group(1)):
            assign = re.sub(r"^\s*(?:(?:parameter|localparam|integer|int|logic|bit|signed|unsigned)\s+)*(?:\[[^\]]*\]\s*)?", "", assign)
            am = re.match(r"\s*(\w+)\s*=\s*(.+?)\s*\)?\s*$", assign)
            if am:
                v = _eval_int(am.group(2), out)
                if v is not None:
                    out[am.group(1)] = v
    return out


def parse_ports(src: str, module: str = "RefModule", lenient: bool = False) -> tuple[Port, ...]:
    """Parse an ANSI-style port list. Handles type keywords, initializers and parameterized ranges.
    lenient=True (used for Builder designs): a width that can't be computed is reported as -1."""
    clean = _strip_comments(src)
    m = re.search(rf"module\s+{module}\s*(#\s*\((?:[^()]|\([^()]*\))*\))?\s*\((.*?)\)\s*;", clean, re.S)
    if not m:
        raise ValueError(f"could not find module {module} header")
    params = _params(m.group(1), clean[m.end():])
    ports: list[Port] = []
    direction, msb, lsb, width = None, 0, 0, 1
    for raw in _split_top(m.group(2)):
        part = " ".join(raw.split())
        if not part:
            continue
        part = re.sub(r"\s*=.*$", "", part)  # initializer: `output reg q = 1'b0`
        dm = re.match(r"(input|output|inout)\b\s*(.*)", part)
        if dm:
            direction, rest = dm.group(1), dm.group(2)
            rest = re.sub(r"\b(wire|reg|logic|signed|unsigned|var|tri|bit)\s*\[", r"\1 [", rest)  # `reg[7:0] q`
            words = rest.split()
            while words and words[0] in _TYPE_WORDS:
                words.pop(0)
            rest = " ".join(words)
            rm = re.match(r"\[\s*([^:\]]+?)\s*:\s*([^\]]+?)\s*\]\s*(.*)", rest)
            if rm:
                hi, lo = _eval_int(rm.group(1), params), _eval_int(rm.group(2), params)
                rest = rm.group(3)
                if hi is None or lo is None:
                    if not lenient:
                        raise ValueError(f"cannot compute range in {part!r}")
                    msb, lsb, width = 0, 0, -1
                else:
                    msb, lsb, width = hi, lo, abs(hi - lo) + 1
            else:
                msb, lsb, width = 0, 0, 1
        else:
            rest = part  # continuation: "input a, b" shares direction and range
        tokens = rest.strip().split()
        name = tokens[-1] if tokens else None
        if direction is None or not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"unparseable port fragment: {part!r}")
        ports.append(Port(name, direction, width, msb, lsb))
    return tuple(ports)


@lru_cache(maxsize=1)
def load_problems() -> dict[str, Problem]:
    d = config.RAW_DATASET_DIR
    if not d.exists():
        raise FileNotFoundError(f"VerilogEval dataset not found at {d}. See README for setup.")
    problems: dict[str, Problem] = {}
    for prompt_path in sorted(d.glob("*_prompt.txt")):
        pid = prompt_path.name[: -len("_prompt.txt")]
        if pid in EXCLUDED:
            continue
        ref_path = d / f"{pid}_ref.sv"
        test_path = d / f"{pid}_test.sv"
        ports = parse_ports(ref_path.read_text())
        problems[pid] = Problem(pid, prompt_path.read_text().strip(), ports, str(ref_path), str(test_path))
    return problems


def ref_source(problem: Problem) -> str:
    """Reference design. HARNESS USE ONLY: never put this in an agent prompt."""
    with open(problem.ref_path) as f:
        return f.read()


def make_splits(seed: int = config.SPLIT_SEED, sizes: dict | None = None) -> dict[str, list[str]]:
    """Stratified by combinational vs sequential so every split has a similar mix."""
    sizes = sizes or config.SPLIT_SIZES
    problems = load_problems()
    rng = random.Random(seed)
    groups = {
        "seq": sorted(p.id for p in problems.values() if p.is_sequential),
        "comb": sorted(p.id for p in problems.values() if not p.is_sequential),
    }
    total = len(problems)
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for ids in groups.values():
        rng.shuffle(ids)
        frac = len(ids) / total
        n_train = round(sizes["train"] * frac)
        n_val = round(sizes["val"] * frac)
        splits["train"] += ids[:n_train]
        splits["val"] += ids[n_train : n_train + n_val]
        splits["test"] += ids[n_train + n_val :]
    for k in splits:
        splits[k].sort()
    return splits


def load_splits(create: bool = True) -> dict[str, list[str]]:
    """Splits are chosen once and locked in data/splits.json."""
    if config.SPLITS_PATH.exists():
        return json.loads(config.SPLITS_PATH.read_text())
    if not create:
        raise FileNotFoundError(config.SPLITS_PATH)
    splits = make_splits()
    config.SPLITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SPLITS_PATH.write_text(json.dumps({"seed": config.SPLIT_SEED, **splits}, indent=2))
    return json.loads(config.SPLITS_PATH.read_text())


def split_problems(name: str, limit: int | None = None) -> list[Problem]:
    problems = load_problems()
    ids = load_splits()[name]
    if limit:
        ids = ids[:limit]
    return [problems[i] for i in ids]
