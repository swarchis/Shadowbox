"""Test-time selection: pick one of several Builder drafts with no reference available.

1. Drop drafts that don't compile or don't match the interface.
2. Get a stimulus: the Breaker's multi-draft attack (mode 'breaker') or random inputs (mode 'random').
3. Simulate all drafts together and group the ones that behave identically.
4. The largest group wins. If the top groups tie, a Judge agent reads the spec and the disputed input.
"""
from __future__ import annotations

import asyncio

from . import config, harness, prompts
from .breaker import attack_multi
from .dataset import Problem
from .llm import FatalLLMError, LLMClient, SpendCapExceeded, extract_json
from .playbook import Playbook


async def _judge(problem: Problem, groups: list[list[str]], gr: harness.GroupResult, llm: LLMClient, tag: str) -> tuple[int, str]:
    """Ask the judge which tied group matches the spec. Returns (group index, reasoning)."""
    reps = [g[0] for g in groups]
    samples = gr.trace.samples if gr.trace else []
    upto = 0
    for s in samples:  # first point where the TIED groups (not just any groups) disagree
        if all(r in s.outputs for r in reps) and len({tuple(sorted(s.outputs[r].items())) for r in reps}) > 1:
            upto = s.cycle
            break
    history = [s for s in samples if s.cycle <= upto and all(r in s.outputs for r in reps)]
    lines = []
    for s in history[-12:]:
        outs = "; ".join(f"group {gi}: " + ", ".join(f"{k}={v}" for k, v in s.outputs.get(g[0], {}).items()) for gi, g in enumerate(groups))
        lines.append(f"cycle {s.cycle} ({s.phase}) inputs {s.inputs} -> {outs}")
    user = (f"Specification:\n{problem.spec}\n\nPorts:\n{problem.ports_summary()}\n\n"
            f"Behavior of each group, up to the first disagreement (values in binary):\n" + "\n".join(lines))
    try:
        r = await llm.chat(role="judge", model_key="judge", temperature=config.WORK_TEMPERATURE, tag=f"{tag}:judge",
                           messages=[{"role": "system", "content": prompts.JUDGE_SYSTEM}, {"role": "user", "content": user}],
                           meta={"problem_id": problem.id, "n_groups": len(groups), "tag": tag})
        data = extract_json(r.text)
        g = int(data.get("group", 0))
        if 0 <= g < len(groups):
            return g, str(data.get("reasoning", ""))[:400]
    except (SpendCapExceeded, FatalLLMError):
        raise
    except Exception as e:
        return 0, f"judge failed ({type(e).__name__}); defaulted to first group"
    return 0, "judge returned an invalid group; defaulted to first group"


async def select(problem: Problem, drafts: dict[str, str | None], *, mode: str, breaker_pb: Playbook | None,
                 llm: LLMClient, tag: str, seed: int = 0) -> dict:
    """Returns a selection record (see /api/selection-examples in docs/CONTRACT.md, minus official grades)."""
    rec = {"problem_id": problem.id, "mode": mode, "groups": [], "chosen_group": None, "chosen_label": None,
           "decided_by": "none", "judge_reasoning": None, "disputed": None, "stimulus_cycles": 0, "error": None}
    compiled = {}
    for lab, code in drafts.items():
        if code and (await asyncio.to_thread(harness.compile_check, problem, code)).ok:
            compiled[lab] = code
    rec["compiled_labels"] = sorted(compiled)
    if not compiled:
        return rec
    if len(compiled) == 1:
        lab = next(iter(compiled))
        rec.update(groups=[[lab]], chosen_group=0, chosen_label=lab, decided_by="single")
        return rec

    if mode == "breaker":
        a = await attack_multi(problem, compiled, breaker_pb, llm, tag=tag)
        stimulus = a.stimulus
        if stimulus is None:
            rec["error"] = a.error or "breaker produced no stimulus"
            rec["api_error"] = bool(a.api_error)  # an API failure is retried later, not scored
            lab = sorted(compiled)[0]
            rec.update(groups=[sorted(compiled)], chosen_group=0, chosen_label=lab, decided_by="fallback")
            return rec
    elif mode == "random":
        stimulus = harness.random_stimulus(problem, config.RANDOM_STIMULUS_CYCLES, seed=seed)
    else:
        raise ValueError(mode)
    rec["stimulus_cycles"] = len(stimulus)

    gr = await asyncio.to_thread(harness.group_by_behavior, problem, compiled, stimulus)
    rec["error"] = gr.error
    groups = gr.groups
    rec["groups"] = groups
    if gr.first_disagreement:
        rec["disputed"] = gr.first_disagreement
    if len(groups) == 1 or len(groups[0]) > len(groups[1]):
        rec.update(chosen_group=0, chosen_label=groups[0][0], decided_by="majority")
        return rec
    tied = [g for g in groups if len(g) == len(groups[0])]
    gi, why = await _judge(problem, tied, gr, llm, tag)
    rec.update(chosen_group=groups.index(tied[gi]), chosen_label=tied[gi][0], decided_by="judge", judge_reasoning=why)
    return rec
