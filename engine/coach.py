"""Coaches: read a round's training results and propose playbook changes; validate and apply them."""
from __future__ import annotations

import re

from . import config, prompts, store
from .dataset import load_problems
from .llm import FatalLLMError, LLMClient, SpendCapExceeded, extract_json, fenced_blocks
from .playbook import Playbook, history_for_coach, read_lineage
from .tools_runner import run_tool, screen_tool_code

CHANGE_TYPES = {"rule_add", "rule_remove", "prompt_edit", "tool_add", "tool_remove", "param", "memory_add"}
PARAMS = {
    "builder": {"max_debug_attempts": (int, 1, 3), "use_planner": (bool, None, None), "drafts": (int, 1, 5),
                "think": (str, ("off", "low", "on"), None), "reference": (bool, None, None), "memory_k": (int, 0, 4)},
    "breaker": {"max_cycles": (int, 8, config.STIMULUS_MAX_CYCLES)},
}
ROLES = {"builder": ["planner", "writer", "debugger"], "breaker": ["attacker", "multi_attacker"]}
MAX_REPORT_CHARS = 20000  # shorter prompt = faster coach


def _clip(s: str | None, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "\n...[truncated]"


def builder_evidence(match: dict) -> tuple[str, list[str]]:
    """Failure report for the Builder coach and the ids of failing problems."""
    probs = load_problems()
    failing, parts = [], []
    passing = [r["problem_id"] for r in match["problems"] if r["official"]["passed"] and r["hard_pass"]]
    for r in match["problems"]:
        attack = r.get("attack") or {}
        if r["official"]["passed"] and r["hard_pass"]:
            continue
        failing.append(r["problem_id"])
        why = []
        if not r["build"]["compiled"]:
            why.append("did not compile / interface mismatch")
        off = r["official"]
        if not off["passed"]:
            why.append(f"official test: {off['kind']}" + (f", {off['mismatches']} mismatching samples" if off.get("mismatches") else ""))
            why += off.get("hints", [])[:4]
        if attack.get("valid_bug"):
            fm = attack.get("first_mismatch") or {}
            why.append(f"Breaker found a bug: at cycle {fm.get('cycle')} ({fm.get('phase')}) with inputs {fm.get('inputs')}, "
                       f"output '{fm.get('signal')}' should be {fm.get('expected')} but was {fm.get('got')}")
        tools = [t for t in r["build"].get("tool_reports", []) if t.get("fired")]
        if tools:
            why.append("tools fired: " + "; ".join(f"{t['tool']}: {', '.join(t.get('findings', []))}" for t in tools))
        parts.append(
            f"### {r['problem_id']}\nSpec:\n{_clip(probs[r['problem_id']].spec, 1200)}\n"
            f"Builder code:\n```verilog\n{_clip(r['build'].get('code'), 2500)}```\nWhy it failed:\n- " + "\n- ".join(why)
        )
    examples = []
    for r in match["problems"]:  # a few short passing designs, so the coach sees what must NOT change
        if r["official"]["passed"] and r["hard_pass"] and r["build"].get("code") and len(examples) < 3 and len(r["build"]["code"]) < 900:
            examples.append(f"### {r['problem_id']} (PASSING)\nSpec:\n{_clip(probs[r['problem_id']].spec, 400)}\n"
                            f"Code:\n```verilog\n{r['build']['code']}```")
    report = (f"Passed ({len(passing)}): {', '.join(passing) or 'none'}\n\nFailed ({len(failing)}):\n\n" + "\n\n".join(parts)
              + ("\n\nPassing examples (your change must not break these):\n\n" + "\n\n".join(examples) if examples else ""))
    return _clip(report, MAX_REPORT_CHARS), failing


def breaker_evidence(match: dict) -> tuple[str, list[str]]:
    """Which buggy designs the attack exposed vs missed. 'Missed' = official test fails but the attack found nothing."""
    probs = load_problems()
    hits, misses, parts = [], [], []
    for r in match["problems"]:
        attack = r.get("attack")
        if not attack:
            continue
        buggy = not r["official"]["passed"]
        if attack.get("valid_bug"):
            hits.append(r["problem_id"])
            continue
        if buggy and r["build"]["compiled"]:
            misses.append(r["problem_id"])
            parts.append(
                f"### {r['problem_id']} (MISSED: design is buggy but the attack exposed nothing)\nSpec:\n{_clip(probs[r['problem_id']].spec, 1000)}\n"
                f"Design:\n```verilog\n{_clip(r['build'].get('code'), 2000)}```\n"
                f"Attack: {attack.get('stimulus_cycles', 0)} cycles. {attack.get('error') or ''}\n"
                f"Hidden official test hints: {'; '.join(r['official'].get('hints', [])[:3])}"
            )
    report = (f"Attacks that exposed a real bug ({len(hits)}): {', '.join(hits) or 'none'}\n\n"
              f"Missed buggy designs ({len(misses)}):\n\n" + "\n\n".join(parts))
    return _clip(report, MAX_REPORT_CHARS), misses


def _tried(team: str) -> list[str]:
    out = []
    for e in read_lineage():
        if e["team"] != team or e["accepted"]:
            continue
        out.append(f"tool:{e['tool_name']}" if e.get("tool_name") else e.get("rule_text") or e["summary"])
    return out


async def propose(team: str, pb: Playbook, match: dict, llm: LLMClient, *, k: int, round_no: int,
                  model_key: str = "coach") -> tuple[list[dict], list[str], float]:
    """Returns (proposals, evidence problem ids, cost)."""
    report, evidence = (builder_evidence if team == "builder" else breaker_evidence)(match)
    template = prompts.BUILDER_COACH_SYSTEM if team == "builder" else prompts.BREAKER_COACH_SYSTEM
    system = template.format(margin=config.GATE_MARGIN, roles=", ".join(ROLES[team]), tool_min=config.TOOL_MIN_PROBLEMS,
                             cap=config.TOOLBOX_CAP, k=k)
    if k >= 3:  # force exploration across change types, so structural ideas actually get measured
        system += ("\n\nDIVERSITY REQUIREMENT: your proposals must be of different kinds. Include exactly one rule change "
                   "(rule_add, rule_remove or prompt_edit), exactly one tool change (tool_add or tool_remove), and exactly one "
                   "\"param\" change" + (" (for example \"think\", \"drafts\" for a team-structure change, or \"use_planner\")" if team == "builder" else "")
                   + ". Any further proposals may be of any kind.")
    current = (f"Current playbook (version {pb.version}):\nRules:\n" + ("\n".join(f"{i}. {r}" for i, r in enumerate(pb.rules)) or "(none)") +
               f"\nTools: {', '.join(pb.tools) or '(none)'}\nParams: {pb.params}\n"
               + "\n".join(f"Prompt '{role}':\n{text}\n" for role, text in pb.prompts.items()))
    user = (f"{current}\nHistory of past proposals:\n{history_for_coach(team)}\n\n"
            f"Round {round_no} results on training problems:\n{report}")
    meta = {"team": team, "round": round_no, "rules": pb.rules, "tools": pb.tools, "evidence": evidence, "k": k, "tried": _tried(team)}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    cost, proposals = 0.0, []
    for attempt in range(2):  # one repair turn if the reply isn't usable JSON
        try:
            r = await llm.chat(role="coach", model_key=model_key, messages=messages, temperature=0.3,
                               tag=f"r{round_no}:{team}_coach", meta=meta)
        except (SpendCapExceeded, FatalLLMError):
            raise
        except Exception as e:  # API still failing after retries: this round gets no proposals, the run goes on
            store.event("coach_error", f"{team.title()} coach call failed ({type(e).__name__}: {str(e)[:160]}); "
                        "no proposals this round", round=round_no, team=team)
            return [], evidence, cost
        cost += r.cost_usd
        try:
            proposals = parse_proposals(r.text, k)
            break
        except ValueError as e:
            store.event("coach_parse", f"{team.title()} coach reply unusable ({e}); asking for a corrected reply", round=round_no, team=team)
            messages = messages + [{"role": "assistant", "content": r.text},
                                   {"role": "user", "content": f"Your reply could not be used: {e}. Reply again with the proposals in the "
                                                               "exact output format: one ```json block, and tool code only in separate "
                                                               "```python blocks starting with `# tool: <name>`."}]
    return proposals, evidence, cost


def parse_proposals(text: str, k: int) -> list[dict]:
    """JSON proposals plus tool code from `# tool: <name>` python blocks. Raises ValueError if unusable."""
    data = extract_json(text)
    props = data.get("proposals") if isinstance(data, dict) else data
    if not isinstance(props, list):
        raise ValueError('expected {"proposals": [...]}')
    props = [p for p in props if isinstance(p, dict)][:k]
    if not props:
        raise ValueError("no proposal objects found")
    tool_blocks = {}
    for lang, body in fenced_blocks(text):
        m = re.match(r"\s*#\s*tool:\s*(\w+)\s*\n", body)
        if lang in ("python", "py", "") and m:
            tool_blocks[m.group(1)] = body[m.end():]
    for p in props:
        if p.get("change_type") == "tool_add":
            code = p.get("tool_code")
            name = p.get("tool_name")
            if (not isinstance(code, str) or "def run" not in code) and isinstance(name, str) and name in tool_blocks:
                p["tool_code"] = tool_blocks[name]
    return props


def apply(pb: Playbook, prop: dict, evidence_ids: list[str], cand_id: str) -> tuple[Playbook | None, str | None]:
    """Validate a proposal and produce the candidate playbook. Returns (candidate, None) or (None, reason)."""
    team = pb.team
    ct = prop.get("change_type")
    if not isinstance(ct, str) or ct not in CHANGE_TYPES:
        return None, f"unknown change_type {ct!r}"
    cand = pb.clone()
    cand.version, cand.parent = cand_id, pb.version
    if ct == "rule_add":
        rule = prop.get("rule")
        rule = rule.strip() if isinstance(rule, str) else ""
        if not rule or len(rule) > 400:
            return None, "rule missing or too long"
        if rule in cand.rules:
            return None, "rule already present"
        cand.rules.append(rule)
    elif ct == "rule_remove":
        idx = prop.get("rule_index")
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(cand.rules):
            return None, "bad rule_index"
        cand.rules.pop(idx)
    elif ct == "prompt_edit":
        role, text = prop.get("role"), prop.get("prompt")
        text = text.strip() if isinstance(text, str) else ""
        if not isinstance(role, str) or role not in ROLES[team] or len(text) < 40:
            return None, "bad role or prompt too short"
        if team == "breaker" and '"cycles"' not in text:
            return None, "breaker prompt must keep the JSON stimulus format"
        cand.prompts[role] = text
    elif ct == "tool_add":
        name, code = prop.get("tool_name"), prop.get("tool_code")
        if not isinstance(name, str) or not name.isidentifier():
            return None, "tool_name must be a Python identifier"
        if not isinstance(code, str) or "def run" not in code:
            return None, "tool code missing (put it in a ```python block starting with `# tool: <name>`)"
        if name in cand.tools:
            return None, "tool already in toolbox"
        if len(cand.tools) >= config.TOOLBOX_CAP:
            return None, f"toolbox is full ({config.TOOLBOX_CAP}); remove a tool first"
        ev = prop.get("evidence_problems")
        cited = {e for e in ev if isinstance(e, str)} & set(evidence_ids) if isinstance(ev, list) else set()
        if len(cited) < config.TOOL_MIN_PROBLEMS:
            return None, f"tool needs evidence from {config.TOOL_MIN_PROBLEMS}+ failing problems (cited {len(cited)} valid)"
        issues = screen_tool_code(code)
        if issues:
            return None, "tool rejected by static screen: " + "; ".join(issues)
        smoke = run_tool(code, "A one-bit inverter.", "module TopModule(input a, output y);\n  assign y = ~a;\nendmodule\n",
                         [{"name": "a", "direction": "input", "width": 1}, {"name": "y", "direction": "output", "width": 1}])
        if smoke.get("error"):
            return None, f"tool crashed on a smoke test: {smoke['error']}"
        cand.tools.append(name)
        cand.tool_sources[name] = code
    elif ct == "tool_remove":
        name = prop.get("tool_name")
        if not isinstance(name, str) or name not in cand.tools:
            return None, "no such tool"
        cand.tools.remove(name)
        cand.tool_sources.pop(name, None)
    elif ct == "memory_add":  # system-generated from this round's verified solutions (never from the coach)
        from .memory import MEMORY_CAP

        entries = [e for e in (prop.get("entries") or []) if isinstance(e, dict) and e.get("code") and e.get("problem_id")]
        known = {m["problem_id"] for m in cand.memory}
        new_entries = [e for e in entries if e["problem_id"] not in known]
        if not new_entries:
            return None, "no new verified solutions to remember"
        cand.memory = (cand.memory + new_entries)[-MEMORY_CAP:]
        if not cand.params.get("memory_k"):
            cand.params["memory_k"] = 2
    elif ct == "param":
        pname = prop.get("param")
        spec = PARAMS[team].get(pname) if isinstance(pname, str) else None
        if not spec:
            return None, f"unknown param {prop.get('param')!r}"
        typ, lo, hi = spec
        val = prop.get("value")
        if typ is bool:
            if not isinstance(val, bool):
                return None, "value must be true/false"
        elif typ is str:
            if val not in lo:
                return None, f"value must be one of {list(lo)}"
        else:
            if not isinstance(val, int) or isinstance(val, bool) or not lo <= val <= hi:
                return None, f"value must be an int in [{lo}, {hi}]"
        if cand.params.get(pname) == val:
            return None, "parameter already has that value"
        cand.params[pname] = val
    return cand, None
