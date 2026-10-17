"""Offline stand-in for the LLM, used only when no CRUSOE_API_KEY is set (or SHADOWBOX_MOCK=1).

Purpose: exercise every code path (parsing, harness, gating, checkpoints, UI) without spending money.
It is NOT a model of real behavior and its numbers mean nothing. Output goes to runs_mock/ and
versions_mock/, and every UI screen shows a MOCK DATA badge.

To produce designs it reads the reference solution and sometimes injects a bug, which real agents
can never do. That is acceptable only because this module is never loaded in real mode
(see LLMClient.__init__).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re

from . import dataset, harness

LATENCY_S = float(os.environ.get("SHADOWBOX_MOCK_LATENCY", "0.03"))


def _u(*parts) -> float:
    """Deterministic uniform [0,1) from the given parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:12], 16) / float(16**12)


# Canned coach material. The mock writer/attacker reward or penalize these exact rule texts, so the
# gate sees a mix of good, neutral and harmful proposals (some accepted, some rejected).
BUILDER_RULES = {
    "Inside clocked always blocks use non-blocking assignments (<=); use blocking (=) only in combinational blocks.": 0.10,
    "Implement resets exactly as specified: synchronous resets inside the clocked block, asynchronous resets also in the sensitivity list.": 0.08,
    "Give every output a value on every path of combinational logic (assign defaults before case/if) so no latches are inferred.": 0.06,
    "Check the width and bit order of every vector port against the specification before writing logic.": 0.05,
    "Do not add registers, pipeline stages or ports the specification does not ask for.": 0.03,
    "Write a comment describing every state of a state machine before implementing it.": -0.01,
    "Prefer SystemVerilog interfaces and packages to plain ports for clarity.": -0.08,
    "When unsure, register every output on the clock edge to avoid glitches.": -0.06,
}

BUILDER_TOOLS = {
    "blocking_in_clocked": (
        0.04,
        '''import re


def run(spec, verilog, ports):
    """Flags blocking assignments inside edge-triggered always blocks."""
    findings = []
    for m in re.finditer(r"always(_ff)?\\s*@\\s*\\(\\s*(posedge|negedge)[^)]*\\)(.*?)(?=\\balways|\\bendmodule)", verilog, re.S):
        body = m.group(3)
        for line in body.splitlines():
            s = line.split("//")[0]
            if re.search(r"[^<>=!]=[^=]", s) and "<=" not in s and not re.search(r"\\bfor\\b", s):
                findings.append("blocking '=' in clocked block: " + s.strip()[:80])
    return {"fired": bool(findings), "findings": findings[:5]}
''',
    ),
    "case_default_check": (
        0.02,
        '''import re


def run(spec, verilog, ports):
    """Flags case statements in combinational logic without a default branch."""
    findings = []
    for m in re.finditer(r"\\bcase[zx]?\\b(.*?)\\bendcase\\b", verilog, re.S):
        if "default" not in m.group(1):
            findings.append("case statement without default branch (possible latch)")
    return {"fired": bool(findings), "findings": findings[:5]}
''',
    ),
}

BREAKER_RULES = {
    "Assert every reset input for the first two cycles, then release it.": 10,
    "For clocked designs use at least 30 cycles and revisit every state at least twice.": 14,
    "Include boundary values on every vector input: all zeros, all ones and alternating bit patterns.": 6,
    "Re-assert reset once in the middle of the sequence to test recovery.": 5,
    "Change only one input per cycle so differences are easy to trace.": -6,
    "Keep stimuli short (under 8 cycles) so failures are easy to read.": -10,
}

BREAKER_TOOLS = {
    "reset_finder": (
        4,
        '''import re


def run(spec, verilog, ports):
    """Finds reset inputs and their polarity so the attacker can drive them deliberately."""
    findings = []
    for p in ports:
        name = p.get("name", "")
        if p.get("direction") == "input" and re.search(r"rst|reset", name):
            active = "low" if name.endswith("n") else "high"
            findings.append(f"reset input '{name}' looks active-{active}; assert it at the start and once mid-sequence")
    return {"fired": bool(findings), "findings": findings}
''',
    ),
}


def _mutations(src: str) -> list[str]:
    ops = [(r"&", "|"), (r"\|", "&"), (r"\+", "-"), (r"1'b1", "1'b0"), (r"1'b0", "1'b1"), (r"==", "!="),
           (r"\^", "&"), (r"<=", "="), (r"~", ""), (r"\bposedge\b", "negedge")]
    cut = src.find(");")
    head, body = src[:cut], src[cut:]
    out = []
    for pat, rep in ops:
        for m in re.finditer(pat, body):
            out.append(head + body[: m.start()] + re.sub(pat, rep, body[m.start():], count=1))
    return out


class MockProvider:
    def __init__(self):
        self._intended: dict[str, str] = {}
        self._calls = 0

    async def respond(self, *, role: str, messages: list[dict], temperature: float, meta: dict) -> str:
        self._calls += 1
        if LATENCY_S:
            await asyncio.sleep(LATENCY_S * (0.5 + random.random()))
        fn = getattr(self, f"_{role}", None)
        if fn is None:
            return "OK"
        if role in ("writer", "debugger", "attacker", "multi_attacker"):
            return await asyncio.to_thread(fn, messages, temperature, meta)
        return fn(messages, temperature, meta)

    # ------------------------------------------------------------ builder
    def _quality(self, meta: dict) -> float:
        p = dataset.load_problems()[meta["problem_id"]]
        base = 0.62 if not p.is_sequential else 0.40
        base += 0.25 * (_u("difficulty", p.id) - 0.5)
        rules = meta.get("rules", [])
        bonus = sum(BUILDER_RULES.get(r, 0.0) for r in rules)
        bonus += sum(BUILDER_TOOLS.get(t, (0.0,))[0] for t in meta.get("tools", []))
        if meta.get("use_planner"):
            bonus += 0.03
        scale = {"worker": 1.0, "ultra": 1.35, "transfer": 0.8}.get(meta.get("model_key", "worker"), 1.0)
        return min(0.97, max(0.03, base * scale + bonus))

    def _design(self, meta: dict, temperature: float) -> str:
        key = meta.get("draft_key", "")
        if key in self._intended:
            return self._intended[key]
        p = dataset.load_problems()[meta["problem_id"]]
        correct = dataset.ref_source(p).replace("module RefModule", "module TopModule")
        noise = random.random() if temperature > 0 else _u("noise", p.id, meta.get("fingerprint", ""))
        u = _u("skill", p.id) * 0.8 + noise * 0.2
        design = correct
        if u >= self._quality(meta):
            muts = _mutations(correct)
            rng = random.Random(f"{p.id}|{noise}")
            rng.shuffle(muts)
            for m in muts[:6]:
                if harness.compile_check(p, m).ok and not harness.run_official(p, m).passed:
                    design = m
                    break
        self._intended[key] = design
        return design

    def _planner(self, messages, temperature, meta):
        return "Outline: identify inputs and outputs, decide combinational vs clocked, list state and reset behavior, then derive each output."

    def _writer(self, messages, temperature, meta):
        design = self._design(meta, temperature)
        if _u("syntax", meta.get("draft_key", "")) < 0.12:  # occasional broken first draft, fixed by the debugger
            design = design.replace(";", "", 1)
        return f"Here is the implementation.\n\n```verilog\n{design}```\n"

    def _debugger(self, messages, temperature, meta):
        return f"Fixed the reported issues.\n\n```verilog\n{self._design(meta, temperature)}```\n"

    # ------------------------------------------------------------ breaker
    def _stimulus(self, meta: dict, temperature: float, salt: str) -> str:
        p = dataset.load_problems()[meta["problem_id"]]
        rules = meta.get("rules", [])
        length = 6 + sum(BREAKER_RULES.get(r, 0) for r in rules) + sum(BREAKER_TOOLS.get(t, (0,))[0] for t in meta.get("tools", []))
        length = int(max(1, min(meta.get("max_cycles", 40), length)))
        seed = f"{p.id}|{meta.get('fingerprint')}|{salt}|{random.random() if temperature > 0 else 0}"
        cycles = harness.random_stimulus(p, length, seed=int(_u(seed) * 1e9))
        if "Assert every reset input for the first two cycles, then release it." not in rules:
            rng = random.Random(seed)
            for c in cycles:
                for k in c:
                    if k in harness.RESET_NAMES:
                        c[k] = rng.getrandbits(1)
        widths = {x.name: x.width for x in p.data_inputs}
        out = [{k: (hex(v) if widths[k] > 4 and i % 2 else v) for k, v in c.items()} for i, c in enumerate(cycles)]
        return f"Attack plan: drive edge cases.\n\n```json\n{json.dumps({'cycles': out})}\n```\n"

    def _attacker(self, messages, temperature, meta):
        return self._stimulus(meta, temperature, meta.get("design_hash", ""))

    def _multi_attacker(self, messages, temperature, meta):
        return self._stimulus(meta, temperature, "multi")

    # ------------------------------------------------------------ judge
    def _judge(self, messages, temperature, meta):
        n = max(1, int(meta.get("n_groups", 2)))
        g = int(_u("judge", meta.get("problem_id"), meta.get("tag", "")) * n)
        return f'```json\n{{"group": {g}, "reasoning": "Group {g} matches the specified behavior for this input."}}\n```'

    # ------------------------------------------------------------ coaches
    def _coach(self, messages, temperature, meta):
        team = meta.get("team", "builder")
        rules_bank = BUILDER_RULES if team == "builder" else BREAKER_RULES
        tools_bank = BUILDER_TOOLS if team == "builder" else BREAKER_TOOLS
        have_rules, have_tools = set(meta.get("rules", [])), set(meta.get("tools", []))
        tried = set(meta.get("tried", []))
        evidence = list(meta.get("evidence", []))
        k = int(meta.get("k", 1))
        rng = random.Random(f"{team}|{meta.get('round')}")
        options = []
        for r in rules_bank:
            if r not in have_rules and r not in tried:
                options.append({"change_type": "rule_add", "rule": r, "summary": r})
        for t, (_, code) in tools_bank.items():
            if t not in have_tools and f"tool:{t}" not in tried and len(evidence) >= 3:
                options.append({"change_type": "tool_add", "tool_name": t, "tool_code": code,
                                "summary": f"Add a '{t}' tool that runs on every draft"})
        rng.shuffle(options)
        proposals = []
        for o in options[:k] or [{"change_type": "param", "param": "max_debug_attempts" if team == "builder" else "max_cycles",
                                  "value": 3 if team == "builder" else 60, "summary": "Adjust a parameter"}]:
            ev = rng.sample(evidence, min(len(evidence), 4)) if evidence else []
            o["evidence_problems"] = ev
            o["reasoning"] = (f"{len(ev)} of this round's failures ({', '.join(e.split('_')[0] for e in ev)}) share the same pattern; "
                              f"this change targets it directly. (mock coach)")
            proposals.append(o)
        return "```json\n" + json.dumps({"proposals": proposals}, indent=1) + "\n```"
