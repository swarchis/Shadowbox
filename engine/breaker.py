"""Breaker team: reads the spec and a design, writes a JSON stimulus meant to expose bugs.

The Breaker never sees the reference. Whether an attack found a real bug is decided afterwards by
the harness (training) or by comparing drafts with each other (test time).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import asdict, dataclass, field

from . import config, harness, store
from .dataset import Problem
from .llm import FatalLLMError, LLMClient, SpendCapExceeded, extract_json
from .playbook import Playbook
from .tools_runner import run_toolbox


@dataclass
class AttackResult:
    problem_id: str
    stimulus: list[dict] | None  # normalized: one dict of input -> int per cycle
    steps: list[dict] = field(default_factory=list)
    tool_reports: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None
    api_error: bool = False  # True when the failure was the API, not the model's output

    def to_dict(self) -> dict:
        return asdict(self)


_LITERAL = re.compile(r"(?<![\"\w])(\d*'[sS]?[bBhHdD][0-9a-fA-FxXzZ_]+|0[xX][0-9a-fA-F_]+|0[bB][01_]+)(?![\"\w])")


def quote_literals(text: str) -> str:
    """Models often write Verilog literals (32'h1f) or bare 0x1f / 0b101 as JSON values; quote them so the
    JSON parses (the harness understands all of these formats)."""
    return _LITERAL.sub(lambda m: '"' + m.group(1) + '"', text)


def _system(pb: Playbook, role: str) -> str:
    return pb.system_prompt(role).replace("{max_cycles}", str(pb.params.get("max_cycles", 40)))


async def _attack(problem: Problem, designs_text: str, pb: Playbook, llm: LLMClient, role: str, *,
                  temperature: float, tag: str, design_for_tools: str, salt: str) -> AttackResult:
    res = AttackResult(problem.id, None)
    if not problem.data_inputs:  # nothing to drive (e.g. a constant output): a few idle cycles is the whole attack
        res.stimulus = [{} for _ in range(4)]
        res.steps.append({"agent": role, "summary": "No inputs to drive; ran 4 idle cycles"})
        return res
    ports = [p.to_dict() for p in problem.ports]
    meta = {
        "problem_id": problem.id,
        "team": "breaker",
        "version": pb.version,
        "fingerprint": pb.fingerprint(),
        "rules": pb.rules,
        "tools": pb.tools,
        "max_cycles": pb.params.get("max_cycles", 40),
        "design_hash": salt,
        "ports": ports,
    }
    hints = ""
    if pb.tools:
        res.tool_reports = await asyncio.to_thread(run_toolbox, pb, problem.spec, design_for_tools, ports)
        fired = [r for r in res.tool_reports if r.get("fired")]
        if fired:
            hints = "\n\nAnalysis tool hints:\n" + "\n".join(f"- {r['tool']}: " + "; ".join(r["findings"]) for r in fired)
    clock_note = (f"The clock input '{problem.clock.name}' is driven by the harness." if problem.is_sequential
                  else "This design is combinational; each cycle is one input vector.")
    user = (f"Specification:\n{problem.spec}\n\nPorts:\n{problem.ports_summary()}\n{clock_note}\n"
            f"Inputs you can drive: {', '.join(p.name for p in problem.data_inputs) or '(none)'}\n\n{designs_text}{hints}")
    messages = [{"role": "system", "content": _system(pb, role)}, {"role": "user", "content": user}]
    try:
        for attempt in range(2):  # one repair attempt on malformed output
            r = await llm.chat(role=role, messages=messages, temperature=temperature, tag=f"{tag}:{role}", meta=meta,
                               thinking=config.BREAKER_THINKING,
                               max_tokens=8192 if config.BREAKER_THINKING != "off" else None)
            res.cost_usd += r.cost_usd
            try:
                stim = harness.normalize_stimulus(problem, extract_json(quote_literals(r.text)))
                max_cycles = int(pb.params.get("max_cycles", 40))
                res.stimulus = stim[:max_cycles]  # the playbook's cycle budget is a hard limit
                res.steps.append({"agent": role, "summary": f"Wrote a {len(res.stimulus)}-cycle attack"
                                  + (f" (trimmed from {len(stim)})" if len(stim) > max_cycles else "")})
                break
            except (ValueError, harness.StimulusError) as e:
                res.error = f"invalid stimulus: {e}"[:300]
                res.steps.append({"agent": role, "summary": res.error})
                hint = (" Your reply was cut off: keep it short and write wide values as quoted hex strings like \"0xff00\"."
                        if r.finish_reason == "length" else "")
                messages += [{"role": "assistant", "content": r.text[-2000:]},
                             {"role": "user", "content": f"That stimulus was rejected: {e}.{hint} Return a corrected stimulus in the required JSON format."}]
        if res.stimulus is not None:
            res.error = None
    except (SpendCapExceeded, FatalLLMError):
        raise
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"[:300]
        res.api_error = True
        store.event("llm_error", f"Breaker call failed on {problem.id}: {res.error}", tag=tag)
    return res


async def attack(problem: Problem, design: str, pb: Playbook, llm: LLMClient, *,
                 temperature: float = config.WORK_TEMPERATURE, tag: str = "") -> AttackResult:
    """Training-time attack on one Builder design."""
    salt = hashlib.sha1(design.encode()).hexdigest()[:10]
    text = f"Design under test:\n```verilog\n{design}```"
    return await _attack(problem, text, pb, llm, "attacker", temperature=temperature, tag=tag, design_for_tools=design, salt=salt)


async def attack_multi(problem: Problem, drafts: dict[str, str], pb: Playbook, llm: LLMClient, *,
                       temperature: float = config.WORK_TEMPERATURE, tag: str = "") -> AttackResult:
    """Test-time attack: find inputs on which the candidate drafts disagree."""
    text = "\n\n".join(f"Candidate {lab}:\n```verilog\n{code}```" for lab, code in drafts.items())
    first = next(iter(drafts.values()))
    return await _attack(problem, text, pb, llm, "multi_attacker", temperature=temperature, tag=tag, design_for_tools=first, salt="multi")
