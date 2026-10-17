"""The self-play loop. Every step writes its result to disk before the next starts; rerunning resumes.

setup:  v0 playbooks -> Builder v0 on validation -> frozen bug pool -> Breaker v0 on the pool
round:  match (train) -> Builder coach + gate (validation) -> Breaker coach + gate (bug pool)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from . import coach, config, gatekeeper, harness, playbook, store
from .breaker import attack
from .bug_pool import build_pool, load_pool
from .builder import build
from .dataset import load_problems, load_splits, split_problems
from .llm import LEDGER, LLMClient, SpendCapExceeded


class Ctx:
    def __init__(self, train, val, k: int, coach_model: str = "coach", breaker_enabled: bool = True):
        self.train, self.val, self.k = train, val, k
        self.coach_model = coach_model
        self.breaker_enabled = breaker_enabled


def _state(**kw):
    spent, calls = LEDGER.snapshot()
    return store.update_state(spend_usd=round(spent, 4), llm_calls=calls,
                              builder_version=playbook.current_version("builder"),
                              breaker_version=playbook.current_version("breaker"), **kw)


def round_dir(n: int):
    return store.runs_dir() / f"round_{n}"


def completed_rounds() -> list[int]:
    return sorted(int(p.name.split("_")[1]) for p in store.runs_dir().glob("round_*") if (p / "done.json").exists())


# ------------------------------------------------------------------ setup
async def builder_val(pb, ctx: Ctx, llm) -> dict:
    res = await gatekeeper.builder_results_cached(f"builder_{pb.version}_val", ctx.val, pb, llm, tag=f"val:builder_{pb.version}")
    return res


async def breaker_pool(pb, llm) -> dict:
    return await gatekeeper.breaker_results_cached(f"breaker_{pb.version}_pool", load_pool(), pb, llm, tag=f"pool:breaker_{pb.version}")


async def setup(ctx: Ctx, llm: LLMClient) -> None:
    playbook.ensure_v0()
    b0 = playbook.load("builder", 0)
    _state(phase="bug_pool", step="baseline", message=f"Scoring Builder v0 on {len(ctx.val)} validation problems")
    v0_val = await builder_val(b0, ctx, llm)
    store.write_json(store.runs_dir() / "baseline" / "val_v0.json", {"pass_rate": gatekeeper.score(v0_val, "passed"), "results": v0_val})
    store.event("baseline", f"Builder v0 passes {gatekeeper.score(v0_val, 'passed'):.0%} of validation problems")
    if ctx.breaker_enabled:
        _state(phase="bug_pool", step="bug_pool", message="Building the frozen bug pool from Builder v0's mistakes")
        pool = await build_pool(ctx.val, b0, v0_val, llm)
        _state(phase="bug_pool", step="breaker_baseline", message=f"Scoring Breaker v0 on {len(pool)} frozen buggy designs")
        r = await breaker_pool(playbook.load("breaker", 0), llm)
        store.event("baseline", f"Breaker v0 catches {gatekeeper.score(r, 'caught'):.0%} of the frozen bug pool")
    write_series(ctx)


# ------------------------------------------------------------------ match
def _hard_suite_path():
    return store.runs_dir() / "hard_suite.json"


async def run_match(n: int, ctx: Ctx, llm: LLMClient) -> dict:
    path = round_dir(n) / "match.json"
    hit = store.read_json(path)
    if hit:
        return hit
    bpb, kpb = playbook.load_current("builder"), playbook.load_current("breaker")
    _state(phase="round", round=n, step="match", message=f"Round {n}: Builder v{bpb.version} vs Breaker v{kpb.version} on {len(ctx.train)} training problems")
    store.event("match_start", f"Round {n} match: Builder v{bpb.version} vs Breaker v{kpb.version}", round=n)

    prev = store.read_json(round_dir(n - 1) / "match.json") if n > 1 else None
    reuse = {}
    if (prev and prev.get("builder_fingerprint") == bpb.fingerprint() and prev.get("settings") == gatekeeper.settings_key()):
        # temp-0 builds of an unchanged Builder under the same settings are reused (API-errored ones are rebuilt)
        reuse = {r["problem_id"]: r for r in prev["problems"] if not r["build"].get("error")}
    suite = store.read_json(_hard_suite_path(), {}) or {}

    async def one(p):
        if p.id in reuse:
            row = {k: reuse[p.id][k] for k in ("problem_id", "spec", "is_sequential", "official", "build")}
        else:
            b = await build(p, bpb, llm, tag=f"r{n}:match")
            off = await asyncio.to_thread(harness.run_official, p, b.code) if b.code else None
            playbook.record_tool_use("builder", b.tool_reports)
            row = {
                "problem_id": p.id,
                "spec": p.spec,
                "is_sequential": p.is_sequential,
                "official": off.to_dict() if off else {"passed": False, "kind": "no_code", "mismatches": None, "samples": None, "hints": [], "log_tail": ""},
                "build": {"code": b.code, "compiled": b.compiled, "attempts": b.attempts, "steps": b.steps,
                          "tool_reports": b.tool_reports, "error": b.error},
            }
        row["official"].pop("log_tail", None)
        row["attack"] = None
        code = row["build"]["code"]
        if ctx.breaker_enabled and code and row["build"]["compiled"]:
            a = await attack(p, code, kpb, llm, tag=f"r{n}:match")
            playbook.record_tool_use("breaker", a.tool_reports)
            att = {"stimulus_cycles": len(a.stimulus or []), "valid_bug": False, "caught_by_official": not row["official"]["passed"],
                   "first_mismatch": None, "error": a.error, "stimulus": a.stimulus}
            if a.stimulus:
                chk = await asyncio.to_thread(harness.check_against_ref, p, code, a.stimulus)
                att["valid_bug"], att["first_mismatch"] = chk.valid_bug, chk.first_mismatch
            row["attack"] = att
        # hard suite: official tests + every valid Breaker stimulus collected so far for this problem
        hard = row["official"]["passed"]
        if hard and code:
            for stim in suite.get(p.id, []):
                if (await asyncio.to_thread(harness.check_against_ref, p, code, stim)).valid_bug:
                    hard = False
                    break
        if row["attack"] and row["attack"]["valid_bug"]:
            hard = False
        row["hard_pass"] = bool(hard)
        return row

    rows = await asyncio.gather(*(one(p) for p in ctx.train))
    for r in rows:  # grow the hard suite with this round's valid attacks
        a = r.get("attack")
        if a and a["valid_bug"] and a.get("stimulus"):
            lst = suite.setdefault(r["problem_id"], [])
            if a["stimulus"] not in lst and len(lst) < 5:
                lst.append(a["stimulus"])
    store.write_json(_hard_suite_path(), suite)
    attacked = [r for r in rows if r["attack"]]
    summary = {
        "train_pass": sum(r["official"]["passed"] for r in rows) / len(rows),
        "hard_pass": sum(r["hard_pass"] for r in rows) / len(rows),
        "bugs_found": sum(bool(r["attack"]["valid_bug"]) for r in attacked),
        "subtle_bugs": sum(bool(r["attack"]["valid_bug"] and r["official"]["passed"]) for r in attacked),
        "problems": len(rows),
    }
    match = {"round": n, "builder_version": bpb.version, "breaker_version": kpb.version, "builder_fingerprint": bpb.fingerprint(),
             "settings": gatekeeper.settings_key(),
             "summary": summary, "problems": sorted(rows, key=lambda r: r["problem_id"])}
    store.write_json(path, match)
    store.event("match_done", f"Round {n}: Builder passes {summary['train_pass']:.0%} of train; Breaker found {summary['bugs_found']} real bugs "
                f"({summary['subtle_bugs']} missed by the official tests)", round=n)
    return match


# ------------------------------------------------------------------ gates
def _find_version(team: str, fingerprint: str, round_no: int) -> int | None:
    for v in range(1, playbook.current_version(team) + 2):
        try:
            pb = playbook.load(team, v)
        except FileNotFoundError:
            continue
        if pb.created_round == round_no and pb.fingerprint() == fingerprint:
            return v
    return None


# Settings the team sweeps through on its own, one per round, in this order (the coach rarely explores them).
SWEEP = {"builder": [("think", "low"), ("reference", True), ("drafts", 3), ("use_planner", True), ("think", "on")], "breaker": []}


def next_sweep(team: str, cur) -> dict | None:
    tried = {(e.get("param"), json.dumps(e.get("value"))) for e in playbook.read_lineage() if e["team"] == team and e.get("param")}
    for name, value in SWEEP.get(team, []):
        if cur.params.get(name) != value and (name, json.dumps(value)) not in tried:
            return {"change_type": "param", "param": name, "value": value, "source": "sweep",
                    "summary": f"Settings sweep: try {name} = {json.dumps(value)}",
                    "reasoning": "Systematic sweep of the team's own settings (not proposed by the coach): each untried "
                                 "setting is tested once on validation and kept only if it measurably helps.",
                    "evidence_problems": []}
    return None


def _tag_cost(prefix: str) -> float:
    return sum(r.get("cost_usd", 0.0) for r in store.read_jsonl(store.ledger_path()) if str(r.get("tag", "")).startswith(prefix))


def _str_list(v, limit: int = 12) -> list[str]:
    return [x for x in v if isinstance(x, str)][:limit] if isinstance(v, list) else []


async def run_gate(team: str, n: int, ctx: Ctx, match: dict, llm: LLMClient) -> dict:
    path = round_dir(n) / f"{team}_gate.json"
    hit = store.read_json(path)
    if hit and hit.get("complete"):
        return hit
    key = "passed" if team == "builder" else "caught"
    unit = "validation problems" if team == "builder" else "frozen buggy designs"

    # 1. proposals (saved before any evaluation so a crash never re-bills the coach)
    prop_path = round_dir(n) / f"{team}_proposals.json"
    saved = store.read_json(prop_path)
    if saved is None:
        cur = playbook.load_current(team)
        _state(phase="round", round=n, step=f"{team}_coach", message=f"Round {n}: {team.title()} coach is reviewing the match")
        proposals, evidence, cost = await coach.propose(team, cur, match, llm, k=ctx.k, round_no=n, model_key=ctx.coach_model)
        sweep = next_sweep(team, cur)
        if sweep:  # one untried setting of the team's own playbook per round, gated like any other change
            proposals = list(proposals) + [sweep]
        saved = {"from_version": cur.version, "proposals": proposals, "evidence": evidence, "cost_usd": cost}
        store.write_json(prop_path, saved)
    # Always gate against the version the proposals were written for, even if a crash happened after
    # an acceptance was already promoted (resume must not re-apply proposals to the new version).
    cur = playbook.load(team, saved["from_version"])
    proposals, evidence = saved["proposals"], saved["evidence"]

    # 2. build candidates (invalid proposals are recorded as rejected without spending on evaluation)
    if team == "breaker" and not load_pool():
        store.event("gate_skipped", f"Round {n}: Breaker gate skipped (no bug pool yet)", round=n, team=team)
        proposals = []
    current_res = await (builder_val(cur, ctx, llm) if team == "builder" else breaker_pool(cur, llm))
    before = gatekeeper.score(current_res, key)
    coach_share = saved.get("cost_usd", 0) / max(1, len(proposals))
    entries, cands = [], []
    for i, prop in enumerate(proposals):
        cid = f"r{n}-{team}-c{i}"
        cand, err = coach.apply(cur, prop, evidence, cid)
        ct = prop.get("change_type")
        summary = prop.get("summary") if isinstance(prop.get("summary"), str) else None
        rule = prop.get("rule") if isinstance(prop.get("rule"), str) else None
        e = {"id": cid, "round": n, "team": team, "change_type": ct if isinstance(ct, str) else "unknown",
             "summary": (summary or rule or str(ct))[:200],
             "reasoning": str(prop.get("reasoning") or "")[:1200], "evidence_problems": _str_list(prop.get("evidence_problems")),
             "rule_text": rule, "tool_name": prop.get("tool_name") if isinstance(prop.get("tool_name"), str) else None,
             "param": prop.get("param") if isinstance(prop.get("param"), str) else None, "value": prop.get("value"),
             "source": prop.get("source", "coach"),
             "score_before": round(before, 4), "score_after": None, "gained": [], "lost": [], "net_flips": None, "errors": 0,
             "accepted": False, "from_version": cur.version, "new_version": None, "invalid_reason": err,
             "cost_usd": round(coach_share, 4), "ts": store.now_iso()}
        entries.append(e)
        if cand is not None:
            playbook.save_candidate(cand)
            cands.append((e, cand))
        else:
            store.event("proposal_invalid", f"{team.title()} proposal rejected before testing: {err}", round=n, team=team)

    # 3. evaluate candidates on the same items as the current version
    if cands:
        _state(phase="round", round=n, step=f"{team}_gate", message=f"Round {n}: gating {len(cands)} {team} candidate(s) on {len(current_res)} {unit}")

        async def evaluate(e, cand):
            tag = f"r{n}:gate:{e['id']}"
            if team == "builder":
                res = await gatekeeper.builder_results_cached(f"{e['id']}_val", ctx.val, cand, llm, tag=tag)
            else:
                res = await gatekeeper.breaker_results_cached(f"{e['id']}_pool", load_pool(), cand, llm, tag=tag)
            gained, lost, net = gatekeeper.flips(current_res, res, key)
            e.update(score_after=round(gatekeeper.score(res, key), 4), gained=gained, lost=lost, net_flips=net,
                     errors=max(gatekeeper.n_errors(res), gatekeeper.n_errors(current_res)))
            e["cost_usd"] = round(e["cost_usd"] + _tag_cost(tag), 4)
            return res

        results = await asyncio.gather(*(evaluate(e, c) for e, c in cands))
        best = gatekeeper.decide([e for e, _ in cands])
        if best is not None:
            cand = next(c for e, c in cands if e is best)
            res = next(r for (e, _), r in zip(cands, results) if e is best)
            new_v = _find_version(team, cand.fingerprint(), n) or playbook.promote(cand, n)
            best.update(accepted=True, new_version=new_v)
            new_pb = playbook.load(team, new_v)
            store.write_json(gatekeeper.cache_path(f"{team}_{new_v}_{'val' if team == 'builder' else 'pool'}"),
                             {"fingerprint": new_pb.fingerprint(), "settings": gatekeeper.settings_key(), "version": new_v, "results": res})
            for t in set(cand.tools) - set(cur.tools):
                playbook.set_tool_born(team, t, n)
            store.event("gate_result", f"{team.title()} v{new_v} accepted: \"{best['summary']}\" (+{best['net_flips']} net on {unit})",
                        round=n, team=team, accepted=True)
        for e, _ in cands:
            if not e["accepted"]:
                why = (f"{e['errors']} API errors made the comparison unreliable" if e["errors"] > gatekeeper.MAX_GATE_ERRORS
                       else f"fixed {len(e['gained'])}, broke {len(e['lost'])}; needs net +{config.GATE_MARGIN} or {config.CLEAN_WIN_MIN}+ fixed with none broken")
                store.event("gate_result", f"{team.title()} change rejected: \"{e['summary']}\" ({why})", round=n, team=team, accepted=False)
    playbook.append_lineage([dict(e) for e in entries])
    out = {"round": n, "team": team, "from_version": cur.version, "score_before": before, "entries": entries,
           "accepted_id": next((e["id"] for e in entries if e["accepted"]), None),
           "new_version": playbook.current_version(team), "complete": True}
    store.write_json(path, out)
    return out


# ------------------------------------------------------------------ series
def write_series(ctx: Ctx) -> dict:
    def val_score(v):
        hit = store.read_json(gatekeeper.cache_path(f"builder_{v}_val"))
        return round(gatekeeper.score(hit["results"], "passed"), 4) if hit else None

    def pool_score(v):
        hit = store.read_json(gatekeeper.cache_path(f"breaker_{v}_pool"))
        return round(gatekeeper.score(hit["results"], "caught"), 4) if hit else None

    points = [{"round": 0, "builder_val_pass": val_score(0), "breaker_pool_catch": pool_score(0), "builder_train_pass": None,
               "builder_hard_pass": None, "builder_version": 0, "breaker_version": 0}]
    for n in completed_rounds():
        bg = store.read_json(round_dir(n) / "builder_gate.json", {}) or {}
        kg = store.read_json(round_dir(n) / "breaker_gate.json", {}) or {}
        m = store.read_json(round_dir(n) / "match.json", {}) or {}
        bv = bg.get("new_version", m.get("builder_version", 0))
        kv = kg.get("new_version", m.get("breaker_version", 0))
        points.append({"round": n, "builder_val_pass": val_score(bv), "breaker_pool_catch": pool_score(kv),
                       "builder_train_pass": m.get("summary", {}).get("train_pass"), "builder_hard_pass": m.get("summary", {}).get("hard_pass"),
                       "builder_version": bv, "breaker_version": kv})
    # distinct bugs: the same unchanged design attacked in several rounds counts once
    bugs, subtle = set(), set()
    for n in completed_rounds():
        for r in (store.read_json(round_dir(n) / "match.json", {}) or {}).get("problems", []):
            a = r.get("attack") or {}
            if a.get("valid_bug") and r["build"].get("code"):
                key = (r["problem_id"], hashlib.sha1(r["build"]["code"].encode()).hexdigest())
                bugs.add(key)
                if r["official"].get("passed"):
                    subtle.add(key)
    changes = [{"round": e["round"], "team": e["team"], "accepted": e["accepted"], "summary": e["summary"],
                "net_flips": e["net_flips"] if e["net_flips"] is not None else 0, "invalid": bool(e.get("invalid_reason"))}
               for e in playbook.read_lineage()]
    series = {"points": points, "changes": changes, "gate_margin": config.GATE_MARGIN,
              "distinct_bugs": len(bugs), "distinct_subtle_bugs": len(subtle)}
    store.write_json(store.runs_dir() / "series.json", series)
    return series


# ------------------------------------------------------------------ round + main loop
async def run_round(n: int, ctx: Ctx, llm: LLMClient) -> None:
    if (round_dir(n) / "done.json").exists():
        return
    t0 = time.monotonic()
    match = await run_match(n, ctx, llm)
    await run_gate("builder", n, ctx, match, llm)
    if ctx.breaker_enabled:
        await run_gate("breaker", n, ctx, match, llm)
    store.write_json(round_dir(n) / "done.json", {"completed_at": store.now_iso(), "duration_s": round(time.monotonic() - t0, 1)})
    write_series(ctx)
    _state(phase="round", round=n, step="done", message=f"Round {n} complete")
    store.event("round_done", f"Round {n} complete in {time.monotonic() - t0:.0f}s", round=n)


def _round_durations() -> list[float]:
    out = []
    for n in completed_rounds():
        d = store.read_json(round_dir(n) / "done.json", {}) or {}
        if d.get("duration_s"):
            out.append(float(d["duration_s"]))
    return out


async def run_loop(*, rounds: int | None, minutes: float | None, k: int, reserve_final: bool = False,
                   train_limit: int | None = None, val_limit: int | None = None, coach_model: str = "coach",
                   breaker_enabled: bool = True, llm: LLMClient | None = None) -> Ctx:
    """minutes: stop starting rounds when the next round (plus the final exam, if reserve_final) would not fit.
    When called from `run`, the shared budget in engine.budget is already set and `minutes` is ignored here."""
    from . import budget

    llm = llm or LLMClient()
    load_splits()
    ctx = Ctx(split_problems("train", train_limit), split_problems("val", val_limit), k, coach_model, breaker_enabled)
    if minutes and not budget.BUDGET.enabled:
        budget.set_budget(minutes)
    B = budget.BUDGET
    n_test = len(load_splits()["test"])
    prior = store.read_state()
    resumed = bool(prior.get("started_at"))  # someone restarted the run by hand
    if resumed:
        store.event("resume", "Run resumed by a human (counted as a human intervention)")
    _state(status="running", phase="setup", started_at=prior.get("started_at") or store.now_iso(),
           human_interventions=int(prior.get("human_interventions") or 0) + int(resumed),
           deadline_at=B.deadline_at,
           splits={"train": len(ctx.train), "val": len(ctx.val), "test": len(load_splits()["test"])})
    store.event("run_start", f"Run started ({'mock' if config.MOCK else 'real'} mode): train {len(ctx.train)}, val {len(ctx.val)}, K={k}")
    try:
        await setup(ctx, llm)
        n = (completed_rounds() or [0])[-1] + 1
        while True:
            if rounds is not None and n > rounds:
                break
            if B.enabled:
                durs = _round_durations()
                est_round = (sum(durs[-2:]) / len(durs[-2:])) if durs else 0.0
                est_final = 0.0
                if reserve_final:  # required final work only: vBest + minimum drafts + Breaker selection
                    from .final_eval import DRAFT_MIN

                    v0_pending = not (store.runs_dir() / "final" / "test_v0.json").exists()
                    est_final = budget.seconds_for_work(budget.final_work(n_test, DRAFT_MIN, v0_pending=v0_pending)) * 1.15
                if not B.fits(est_round + est_final):
                    store.event("time_budget", f"Stopping before round {n}: {budget.fmt(B.left())} left; a round takes ~{budget.fmt(est_round)} "
                                f"and the final exam needs ~{budget.fmt(est_final)}")
                    break
            await run_round(n, ctx, llm)
            n += 1
        _state(status="running", phase="round", step="done", message="Self-play finished")
    except SpendCapExceeded as e:
        store.event("spend_cap", str(e))
        _state(status="stopped", message=f"Stopped: {e}")
        raise
    return ctx
