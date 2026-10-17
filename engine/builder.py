"""Builder team: (optional planner) -> writer -> compile/tool check -> debugger loop.

The Builder only ever sees the spec, its own code, compiler output and its own tools' findings.
It never sees the reference or the official testbench result (those exist only for scoring).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from dataclasses import asdict, dataclass, field

from . import config, harness, store
from .dataset import Problem
from .llm import FatalLLMError, LLMClient, SpendCapExceeded, extract_code
from .playbook import Playbook
from .tools_runner import run_toolbox


@dataclass
class BuildResult:
    problem_id: str
    code: str | None
    compiled: bool
    attempts: int
    steps: list[dict] = field(default_factory=list)
    tool_reports: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_REFERENCE_PATH = Path(__file__).parent / "skills" / "verilog_reference.md"


def reference_block(pb: Playbook) -> str:
    """The Verilog reference skill, included only when the playbook turns it on (a gated option)."""
    if not pb.params.get("reference"):
        return ""
    return "\n\nVerilog reference (use it to check your design):\n" + _REFERENCE_PATH.read_text()


def _meta(problem: Problem, pb: Playbook, draft_key: str, model_key: str) -> dict:
    return {
        "problem_id": problem.id,
        "team": "builder",
        "version": pb.version,
        "fingerprint": pb.fingerprint(),
        "rules": pb.rules,
        "tools": pb.tools,
        "use_planner": bool(pb.params.get("use_planner")),
        "draft_key": draft_key,
        "model_key": model_key,
        "ports": [p.to_dict() for p in problem.ports],
    }


async def build(
    problem: Problem,
    pb: Playbook,
    llm: LLMClient,
    *,
    temperature: float = config.WORK_TEMPERATURE,
    model_key: str = "worker",
    tag: str = "",
    draft_index: int = 0,
) -> BuildResult:
    """One Builder answer. With the team-structure param `drafts` = N > 1 (which a coach can propose),
    the team writes N independent drafts and the Breaker picks the one whose behavior the majority
    shares (no reference involved: same mechanism as test-time selection)."""
    n = int(pb.params.get("drafts", 1) or 1)
    if n <= 1:
        return await _build_one(problem, pb, llm, temperature=temperature, model_key=model_key, tag=tag, draft_index=draft_index)
    from . import playbook as _playbook
    from .selector import select

    t = config.DRAFT_TEMPERATURE if temperature == config.WORK_TEMPERATURE else temperature
    results = await asyncio.gather(*(_build_one(problem, pb, llm, temperature=t, model_key=model_key, tag=tag,
                                                draft_index=draft_index * 10 + i) for i in range(n)))
    labels = {f"d{i}": r for i, r in enumerate(results)}
    rec = await select(problem, {lab: r.code for lab, r in labels.items()}, mode="breaker",
                       breaker_pb=_playbook.load_current("breaker"), llm=llm, tag=f"{tag}:team_select")
    chosen = labels.get(rec.get("chosen_label") or "") or next((r for r in results if r.compiled), results[0])
    chosen.cost_usd = sum(r.cost_usd for r in results)
    chosen.error = chosen.error if all(r.error for r in results) else None  # one good draft is enough
    chosen.steps.append({"agent": "breaker", "summary": f"Picked {rec.get('chosen_label') or 'a draft'} of {n} drafts "
                         f"({rec.get('decided_by')}, {len(rec.get('groups') or [])} behavior groups)"})
    return chosen


async def _build_one(
    problem: Problem,
    pb: Playbook,
    llm: LLMClient,
    *,
    temperature: float = config.WORK_TEMPERATURE,
    model_key: str = "worker",
    tag: str = "",
    draft_index: int = 0,
) -> BuildResult:
    draft_key = f"{tag}|{problem.id}|{pb.fingerprint()}|{model_key}|{temperature}|{draft_index}"
    meta = _meta(problem, pb, draft_key, model_key)
    res = BuildResult(problem.id, None, False, 0)
    ports = [p.to_dict() for p in problem.ports]
    user = f"Specification:\n{problem.spec}\n"

    think = str(pb.params.get("think", "off"))

    async def call(role: str, content: str) -> str:
        r = await llm.chat(
            role=role,
            model_key=model_key,
            messages=[{"role": "system", "content": pb.system_prompt(role) + reference_block(pb)},
                      {"role": "user", "content": content}],
            temperature=temperature,
            tag=f"{tag}:{role}",
            meta=meta,
            thinking=think,
            max_tokens=config.THINKING_MAX_TOKENS if think != "off" else None,
        )
        res.cost_usd += r.cost_usd
        if r.finish_reason == "length":  # rambling reply cut off: make sure the debugger knows why
            res.steps.append({"agent": role, "summary": "Reply cut off at the length limit"})
            return r.text + "\n\n[REPLY CUT OFF AT THE LENGTH LIMIT]"
        return r.text

    try:
        if pb.params.get("use_planner"):
            plan = await call("planner", user)
            res.steps.append({"agent": "planner", "summary": plan.strip().splitlines()[0][:160] if plan.strip() else "(empty plan)"})
            user += f"\nDesign outline:\n{plan}\n"

        text = await call("writer", user)
        res.code = extract_code(text)
        res.attempts = 1
        res.steps.append({"agent": "writer", "summary": "Wrote first draft" if res.code else "No code block in answer"})

        max_debug = int(pb.params.get("max_debug_attempts", 2))
        for attempt in range(max_debug + 1):
            if res.code is None:
                feedback, ok = ("Your answer did not contain a complete ```verilog code block with module TopModule "
                                "(it may have been cut off for being too long). Reply with ONLY the module, concisely, "
                                "no explanation."), False
                res.tool_reports = []
            else:
                cc = await asyncio.to_thread(harness.compile_check, problem, res.code)
                reports = await asyncio.to_thread(run_toolbox, pb, problem.spec, res.code, ports) if cc.ok and pb.tools else []
                res.tool_reports = reports
                fired = [r for r in reports if r.get("fired")]
                ok = cc.ok and not fired
                feedback = cc.feedback()
                for r in fired:
                    feedback += f"\nTOOL {r['tool']}: " + "; ".join(r.get("findings", []))
                res.compiled = cc.ok
            if ok or attempt == max_debug:
                break
            prompt = f"{user}\nYour current code:\n```verilog\n{res.code or ''}```\n\nFeedback:\n{feedback}\n"
            text = await call("debugger", prompt)
            new_code = extract_code(text)
            if new_code:
                res.code = new_code
            res.attempts += 1
            res.steps.append({"agent": "debugger", "summary": f"Fixed: {feedback.splitlines()[0][:140]}"})
    except (SpendCapExceeded, FatalLLMError):
        raise  # stop the run: retrying other problems can't help
    except Exception as e:  # transient API failure after retries: marked errored, excluded from scores, retried on rerun
        res.error = f"{type(e).__name__}: {e}"[:300]
        store.event("llm_error", f"Builder call failed on {problem.id}: {res.error}", tag=tag)
    return res
