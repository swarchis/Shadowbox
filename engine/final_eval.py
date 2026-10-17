"""Final exam on the held-out split (official testbenches only), plus the evidence for the pitch.

Required:  Builder v0, Builder vBest, vBest + Breaker selection over temp-0.7 drafts.
Free:      random pick, ceiling, random-input selection (same drafts, no extra model calls).
Optional:  selection with Breaker v0, plain Ultra, Gemma transfer (v0 vs vBest playbook).
Every step is cached under RUNS_DIR/final/ so a rerun only does the missing work.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random

from . import config, gatekeeper, harness, playbook, store
from .breaker import attack
from .builder import build
from .dataset import load_problems, split_problems
from .llm import LLMClient, SpendCapExceeded
from .selector import select


def fdir():
    return store.runs_dir() / "final"


def _flag(name: str, default: bool = True) -> bool:
    return os.environ.get(name, "1" if default else "0") == "1"


async def eval_test(name: str, pb, llm, *, model_key: str = "worker", limit: int | None = None) -> dict:
    problems = split_problems("test", limit)
    by_id = {p.id: p for p in problems}

    async def compute(ids, on_row):
        store.event("final_step", f"Final exam: {name} ({len(ids)} held-out problems)")
        return await gatekeeper.run_builder_on([by_id[i] for i in ids], pb, llm, tag=f"final:{name}", model_key=model_key, on_row=on_row)

    return await gatekeeper.cached_rows(fdir() / f"{name}.json", pb.fingerprint(), gatekeeper.settings_key(model_key),
                                        sorted(by_id), compute)


async def baselines(llm: LLMClient, limit: int | None = None) -> None:
    """Runs that don't depend on the loop's outcome; launched in parallel with self-play."""
    b0 = playbook.load("builder", 0)
    jobs = [eval_test("test_v0", b0, llm, limit=limit)]
    if _flag("SHADOWBOX_FINAL_ULTRA"):
        jobs.append(eval_test("test_ultra_v0", b0, llm, model_key="ultra", limit=limit))
    if _flag("SHADOWBOX_FINAL_TRANSFER"):
        jobs.append(eval_test("test_transfer_v0", b0, llm, model_key="transfer", limit=limit))
    await asyncio.gather(*jobs)


DRAFT_MIN = 3  # selection needs at least 3 drafts for a majority to mean anything


def _draft_path(i: int):
    return fdir() / f"drafts_d{i}.json"


async def draft_batch(pb, llm, i: int, limit: int | None) -> dict[str, dict]:
    """Draft number i for every held-out problem (temperature DRAFT_TEMPERATURE). Cached per index."""
    problems = split_problems("test", limit)
    by_id = {p.id: p for p in problems}

    raw = pb.clone()  # test-time selection always works on raw single drafts, even if the team itself drafts
    raw.params["drafts"] = 1

    async def one(p):
        b = await build(p, raw, llm, temperature=config.DRAFT_TEMPERATURE, tag="final:draft", draft_index=i)
        off = await asyncio.to_thread(harness.run_official, p, b.code) if b.code else None
        return p.id, {"label": f"d{i}", "code": b.code, "compiled": b.compiled, "official_pass": bool(off and off.passed),
                      "error": b.error}

    async def compute(ids, on_row):
        store.event("final_step", f"Final exam: draft {i + 1} for {len(ids)} held-out problems (temperature {config.DRAFT_TEMPERATURE})")

        async def tracked(x):
            k, row = await one(by_id[x])
            on_row(k, row)
            return k, row

        return dict(await asyncio.gather(*(tracked(x) for x in ids)))

    return await gatekeeper.cached_rows(_draft_path(i), pb.fingerprint(), gatekeeper.settings_key("worker", config.DRAFT_TEMPERATURE),
                                        sorted(by_id), compute)


def load_drafts(pb, ids: list[str], n_max: int) -> tuple[dict[str, list[dict]], int]:
    """All complete draft batches 0..n-1 for this playbook, as {problem: [draft, ...]}."""
    drafts = {pid: [] for pid in ids}
    n = 0
    for i in range(n_max):
        hit = store.read_json(_draft_path(i))
        if (not hit or hit.get("fingerprint") != pb.fingerprint() or sorted(hit["results"]) != sorted(ids)
                or hit.get("settings") != gatekeeper.settings_key("worker", config.DRAFT_TEMPERATURE)):
            break
        for pid in ids:
            drafts[pid].append(hit["results"][pid])
        n += 1
    return drafts, n


def _sel_path(name: str):
    return fdir() / f"selection_{name}.json"


def _drafts_key(drafts: dict[str, list[dict]]) -> str:
    """Identity of the exact drafts a selection ran on (codes per problem)."""
    blob = json.dumps({pid: [d.get("code") for d in ds] for pid, ds in sorted(drafts.items())}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def load_selection(name: str, fp: str, drafts: dict[str, list[dict]], n: int) -> dict | None:
    hit = store.read_json(_sel_path(name))
    if (hit and hit.get("fingerprint") == fp and hit.get("n_drafts") == n and hit.get("drafts_key") == _drafts_key(drafts)
            and sorted(hit["records"]) == sorted(drafts)):
        return hit["records"]
    return None


async def selection(name: str, drafts: dict[str, list[dict]], n: int, mode: str, breaker_pb, llm) -> dict[str, dict]:
    fp = breaker_pb.fingerprint() if breaker_pb else "random"
    hit = load_selection(name, fp, drafts, n)
    todo = sorted(drafts) if hit is None else sorted(pid for pid, r in hit.items() if r.get("api_error"))
    if not todo:
        return hit
    store.event("final_step", f"Final exam: test-time selection ({name}, {n} drafts per problem, {len(todo)} problem(s))")
    problems = load_problems()

    async def one(pid):
        ds = {d["label"]: d["code"] for d in drafts[pid]}
        rec = await select(problems[pid], ds, mode=mode, breaker_pb=breaker_pb, llm=llm, tag=f"final:sel_{name}", seed=7)
        grades = {d["label"]: d["official_pass"] for d in drafts[pid]}
        rec["chosen_correct"] = bool(rec["chosen_label"] and grades.get(rec["chosen_label"]))
        return pid, rec

    recs = dict(hit or {})
    recs.update(dict(await asyncio.gather(*(one(pid) for pid in todo))))
    store.write_json(_sel_path(name), {"fingerprint": fp, "n_drafts": n, "drafts_key": _drafts_key(drafts), "records": recs})
    return recs


# ------------------------------------------------------------------ statistics
def bootstrap_ci(values: list[bool], iters: int = 2000, seed: int = 0) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return [round(stats[int(0.025 * iters)], 4), round(stats[int(0.975 * iters) - 1], 4)]


def metric(label: str, values: list, ci: bool = True) -> dict:
    """values: True/False per problem, or None for a problem that hit an API error (excluded and counted)."""
    ok = [bool(v) for v in values if v is not None]
    return {"label": label, "pass": round(sum(ok) / max(1, len(ok)), 4),
            "ci": bootstrap_ci(ok) if ci else None, "n": len(ok), "errors": len(values) - len(ok)}


# ------------------------------------------------------------------ demo material
def _bits(v: int, w: int) -> str:
    return format(v, f"0{w}b")


async def demo_cases(v0_res, vb_res, vbest_pb, breaker_pb, llm, drafts=None, sel=None, max_cases: int = 4) -> list[dict]:
    """Live Match cases: held-out problems where v0 fails and the latest version passes.
    Fallback when the Builder never improved: v0 fails and the Breaker-selected draft passes."""
    problems = load_problems()
    lineage = [e for e in playbook.read_lineage() if e["team"] == "builder" and e["accepted"]]
    pairs = []  # (pid, v0 row, winner row, winner meta, explanation)
    changes = [{"round": e["round"], "summary": e["summary"]} for e in sorted(lineage, key=lambda e: (e["round"], e["id"]))]
    for pid in sorted(v0_res):
        v0, vb = v0_res[pid], vb_res.get(pid, {})
        if not v0["passed"] and vb.get("passed") and v0.get("code") and v0.get("compiled"):
            # Honest framing: the run does not trace WHICH change fixed this problem, so list them all.
            expl = ({"kind": "builder", "round": changes[-1]["round"],
                     "summary": f"{len(changes)} playbook change{'s' if len(changes) != 1 else ''} kept between version 0 and the latest",
                     "reasoning": "The run does not trace which change fixed this particular problem; these are every change "
                                  "the gatekeeper kept on the way from version 0 to the latest.",
                     "changes": changes, "other_changes": max(0, len(changes) - 1)} if changes else None)
            pairs.append((pid, v0, vb, {"version": vbest_pb.version}, expl))
    if not pairs and drafts and sel:
        for pid in sorted(v0_res):
            v0, rec = v0_res[pid], sel.get(pid, {})
            if v0["passed"] or not v0.get("code") or not v0.get("compiled") or not rec.get("chosen_correct"):
                continue
            win = next(d for d in drafts[pid] if d["label"] == rec["chosen_label"])
            expl = {"kind": "selection", "round": None, "summary": f"Breaker picked draft {win['label']} out of {len(drafts[pid])}",
                    "reasoning": f"The drafts split into {len(rec['groups'])} behavior groups on the Breaker's inputs; "
                                 f"decided by {rec['decided_by']}.", "other_changes": 0}
            pairs.append((pid, v0, {"code": win["code"]}, {"version": "selection"}, expl))
    cases = []
    for pid, v0, vb, vmeta, expl in pairs[: max_cases * 2]:  # a few spares so Breaker-exposed cases can be preferred
        p = problems[pid]
        stim, source = None, "random"
        if breaker_pb is not None:
            a = await attack(p, v0["code"], breaker_pb, llm, tag="final:demo")
            if a.stimulus and (await asyncio.to_thread(harness.check_against_ref, p, v0["code"], a.stimulus)).valid_bug:
                stim, source = a.stimulus, "breaker"
        if stim is None:  # the Breaker's attack didn't expose this bug: show random inputs, labelled as such
            stim = harness.random_stimulus(p, 60, seed=3)
        trace = await asyncio.to_thread(harness.simulate, p, {"v0": v0["code"], "vbest": vb["code"]}, stim, True)
        if trace.error and not trace.samples:
            continue
        widths = {x.name: x.width for x in p.data_inputs}
        rows, first_bad = [], None
        for s in trace.samples:
            if s.phase == "pre":
                continue
            row = {"t": len(rows), "inputs": {k: _bits(v, widths[k]) for k, v in s.inputs.items()},
                   "expected": s.outputs.get("ref", {}), "v0": s.outputs.get("v0", {}), "vbest": s.outputs.get("vbest", {})}
            if first_bad is None and any(
                not harness._ref_matches(row["expected"].get(o.name, ""), row["v0"].get(o.name, "")) for o in p.outputs
            ):
                first_bad = row["t"]
            rows.append(row)
        signals = ([{"name": p.clock.name, "kind": "clock"}] if p.is_sequential else []) + \
                  [{"name": x.name, "kind": "input", "width": x.width} for x in p.data_inputs] + \
                  [{"name": x.name, "kind": "output", "width": x.width} for x in p.outputs]
        start = max(0, (first_bad or 0) - 6)
        rows = rows[start:start + 24]
        for i, r in enumerate(rows):
            r["t"] = i
        cases.append({
            "problem_id": pid, "spec": p.spec,
            "v0": {"version": 0, "code": v0["code"], "official_pass": False},
            "vbest": {"version": vmeta["version"], "code": vb["code"], "official_pass": True},
            "explanation": expl,
            "trace": {"signals": signals, "rows": rows, "source": source,
                      "first_mismatch_row": (first_bad - start) if first_bad is not None else None},
        })
    cases.sort(key=lambda c: c["trace"]["source"] != "breaker")  # Breaker-exposed bugs first (stable otherwise)
    return cases[:max_cases]


def selection_examples(drafts, recs, max_examples: int = 8) -> list[dict]:
    problems = load_problems()
    out = []
    for pid, rec in recs.items():
        ds = drafts[pid]
        some_wrong = any(not d["official_pass"] for d in ds if d["compiled"])
        some_right = any(d["official_pass"] for d in ds)
        interesting = rec["chosen_correct"] and some_wrong and len(rec["groups"]) > 1
        out.append((0 if interesting else 1 if (some_wrong and some_right) else 2, pid, {
            "problem_id": pid, "spec": problems[pid].spec, "drafts": ds, "groups": rec["groups"],
            "chosen_group": rec["chosen_group"], "chosen_label": rec["chosen_label"], "chosen_correct": rec["chosen_correct"],
            "decided_by": rec["decided_by"], "judge_reasoning": rec["judge_reasoning"],
            "disputed": rec["disputed"], "stimulus_cycles": rec["stimulus_cycles"]}))
    out.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in out[:max_examples]]


# ------------------------------------------------------------------ assembly (works on partial results)
def _results(name: str, ids: list[str], pb=None, model_key: str = "worker") -> dict | None:
    """Cached held-out results, only if they match this playbook and the current run settings."""
    hit = store.read_json(fdir() / f"{name}.json")
    if not hit or sorted(hit.get("results", {})) != ids:
        return None
    if pb is not None and hit.get("fingerprint") != pb.fingerprint():
        return None
    if hit.get("settings") != gatekeeper.settings_key(model_key):
        return None
    return hit["results"]


def assemble(*, complete: bool = False, limit: int | None = None, note: str | None = None) -> dict:
    """Build final.json from whatever has finished. Safe to call at any time, including after a hard stop."""
    b0, bbest = playbook.load("builder", 0), playbook.load_current("builder")
    kbest = playbook.load_current("breaker")
    k0 = playbook.load("breaker", 0)
    ids = sorted(p.id for p in split_problems("test", limit))
    tname = config.MODELS["transfer"].split("/")[-1]
    v0 = _results("test_v0", ids, b0, "worker")
    vbest = v0 if bbest.version == 0 else _results("test_vbest", ids, bbest, "worker")
    drafts, n = load_drafts(bbest, ids, 10)
    metrics: dict = {k: None for k in ("v0", "vbest", "vbest_selection", "random_pick", "random_input_sel", "breaker_v0_sel",
                                       "ceiling", "ultra", "transfer_v0", "transfer_vbest", "ablation_nano_coach")}

    sel_meta = store.read_json(_sel_path("breaker_vbest")) or {}
    if sel_meta.get("n_drafts") and sel_meta["n_drafts"] <= n:  # use the draft count the selection actually ran on
        drafts, n = load_drafts(bbest, ids, sel_meta["n_drafts"])

    def ok(res, i):
        return res is not None and i in res and not res[i].get("error")

    def vals(res, among=None):
        return [None if not ok(res, i) else bool(res[i]["passed"]) for i in (among if among is not None else ids)]

    # The headline bars (v0, latest, latest + Breaker, and the selection detail rows) are all computed on
    # ONE common set of problems: those where none of their inputs hit an API error.
    sel = {name: load_selection(name, fp, drafts, n) if n else None
           for name, fp in (("breaker_vbest", kbest.fingerprint()), ("random_inputs", "random"), ("breaker_v0", k0.fingerprint()))}
    common = [i for i in ids
              if (v0 is None or ok(v0, i)) and (vbest is None or ok(vbest, i))
              and (not n or not any(d.get("error") for d in drafts[i]))
              and (sel["breaker_vbest"] is None or not sel["breaker_vbest"][i].get("api_error"))]
    excluded = len(ids) - len(common)
    if v0:
        metrics["v0"] = metric("Version 0", vals(v0, common))
    if vbest:
        metrics["vbest"] = metric("Latest version", vals(vbest, common))
    if n:
        rp = [sum(d["official_pass"] for d in drafts[i]) / n for i in common]
        metrics["random_pick"] = {"label": "Random draft", "pass": round(sum(rp) / max(1, len(rp)), 4), "ci": None, "n": len(rp)}
        metrics["ceiling"] = metric("Best possible pick", [any(d["official_pass"] for d in drafts[i]) for i in common], ci=False)
        for key, name, label, ci in (("vbest_selection", "breaker_vbest", "Latest + Breaker", True),
                                     ("random_input_sel", "random_inputs", "Random-input selection", False),
                                     ("breaker_v0_sel", "breaker_v0", "Selection with Breaker v0", False)):
            recs = sel[name]
            if recs:
                metrics[key] = metric(label, [None if recs[i].get("api_error") else recs[i]["chosen_correct"] for i in common], ci=ci)
    ultra = _results("test_ultra_v0", ids, b0, "ultra")
    if ultra:
        metrics["ultra"] = metric(f"{config.MODELS['ultra'].split('/')[-1]} (v0 playbook)", vals(ultra))
    t0 = _results("test_transfer_v0", ids, b0, "transfer")
    if t0:
        metrics["transfer_v0"] = metric(f"{tname} + v0 playbook", vals(t0))
    tv = t0 if bbest.version == 0 else _results("test_transfer_vbest", ids, bbest, "transfer")
    if tv:
        metrics["transfer_vbest"] = metric(f"{tname} + learned playbook", vals(tv))
    abl = store.read_json(store.runs_dir() / "ablation_nano_coach" / "result.json")
    if abl:
        metrics["ablation_nano_coach"] = {"label": "Gain with Nano coach", "pass": abl["nano_gain"], "ci": None, "n": abl["val_problems"]}
        metrics["ablation_main_coach"] = {"label": "Gain with main coach", "pass": abl.get("main_gain"), "ci": None, "n": abl["val_problems"]}
    spent = sum(r.get("cost_usd", 0) for r in store.read_jsonl(store.ledger_path()) if str(r.get("tag", "")).startswith("final:"))
    notes = ["CIs are 95% bootstrap over held-out problems.",
             f"Selection uses {n} drafts per problem at temperature {config.DRAFT_TEMPERATURE}; other rows use temperature {config.WORK_TEMPERATURE}.",
             "Random draft = expected pass rate of picking one draft uniformly at random."]
    if excluded:
        notes.insert(0, f"{excluded} of {len(ids)} held-out problems excluded from the main comparison because a model call "
                        "failed (API error); rerun `final` to retry them.")
    if note:
        notes.insert(0, note)
    if config.MOCK:
        notes.append("MOCK MODE: these numbers are fake and only test the pipeline.")
    final = {"complete": complete, "test_problems": len(ids), "metrics": metrics, "n_drafts": n,
             "builder_versions": {"v0": 0, "vbest": bbest.version}, "breaker_versions": {"v0": 0, "vbest": kbest.version},
             "cost_usd": round(spent, 4), "notes": notes}
    store.write_json(fdir() / "final.json", final)
    return final


# ------------------------------------------------------------------ main
async def optional_eval(name: str, pb, llm, model_key: str, limit: int | None):
    """An optional comparison: a bad model ID or an API outage skips it with a warning instead of stopping the run."""
    try:
        return await eval_test(name, pb, llm, model_key=model_key, limit=limit)
    except (SpendCapExceeded, asyncio.CancelledError):
        raise
    except Exception as e:  # includes FatalLLMError for a wrong optional model ID
        store.event("optional_failed", f"Skipped optional comparison {name} ({config.MODELS.get(model_key, model_key)}): "
                    f"{type(e).__name__}: {str(e)[:200]}")
        return None


async def run_final(llm: LLMClient | None = None, *, limit: int | None = None, n_drafts: int | None = None,
                    run_missing_baselines: bool = True) -> dict:
    """Required steps always run; extra drafts and optional comparisons only if the time budget allows."""
    from .budget import ATTACK_WEIGHT, BUDGET, fmt, seconds_for_work

    llm = llm or LLMClient()
    n_max = max(DRAFT_MIN, n_drafts or config.TEST_TIME_DRAFTS)
    store.update_state(status="running", phase="final", step="final", message="Final exam on held-out problems")
    store.event("final_start", f"Final exam started on the held-out split (time left: {fmt(BUDGET.left())})")
    b0, bbest = playbook.load("builder", 0), playbook.load_current("builder")
    k0, kbest = playbook.load("breaker", 0), playbook.load_current("breaker")
    n_test = len(split_problems("test", limit))
    ids = sorted(p.id for p in split_problems("test", limit))

    # 1. required: v0 and vBest on held-out, plus the first DRAFT_MIN draft batches, all in flight together
    jobs = [eval_test("test_v0", b0, llm, limit=limit)]
    if bbest.version != 0:
        jobs.append(eval_test("test_vbest", bbest, llm, limit=limit))
    jobs += [draft_batch(bbest, llm, i, limit) for i in range(DRAFT_MIN)]
    await asyncio.gather(*jobs)
    assemble(limit=limit)

    # 2. extra drafts while they fit (each batch must leave time for the Breaker selection)
    sel_s = seconds_for_work(n_test * ATTACK_WEIGHT * 1.2)
    for i in range(DRAFT_MIN, n_max):
        need = seconds_for_work(n_test) + sel_s
        if not BUDGET.fits(need):
            store.event("time_budget", f"Final exam: keeping {i} drafts per problem ({fmt(BUDGET.left())} left, another batch needs ~{fmt(need)})")
            break
        await draft_batch(bbest, llm, i, limit)
    drafts, n = load_drafts(bbest, ids, n_max)

    # 3. required: Breaker selection; free: random-input selection
    store.update_state(step="selection", message=f"Test-time selection over {n} drafts per problem")
    sel_b = await selection("breaker_vbest", drafts, n, "breaker", kbest, llm)
    await selection("random_inputs", drafts, n, "random", None, llm)
    assemble(limit=limit)

    # 4. demo material (a handful of calls)
    store.update_state(step="demo_material", message="Preparing demo cases")
    v0 = _results("test_v0", ids, b0, "worker")
    vbest = v0 if bbest.version == 0 else _results("test_vbest", ids, bbest, "worker")
    demo_key = hashlib.sha1(json.dumps([bbest.fingerprint(), kbest.fingerprint(), _drafts_key(drafts),
                                        sorted((k, bool(r.get("passed"))) for k, r in (v0 or {}).items())]).encode()).hexdigest()[:16]
    cached = store.read_json(fdir() / "demo_cases.json") or {}
    if cached.get("key") != demo_key:  # don't pay for the demo attacks again on a rerun
        cases = await demo_cases(v0, vbest, bbest, kbest, llm, drafts=drafts, sel=sel_b)
        store.write_json(fdir() / "demo_cases.json", {"key": demo_key, "cases": cases})
    store.write_json(fdir() / "selection_examples.json", {"examples": selection_examples(drafts, sel_b)})

    # 5. optional comparisons, each only if it fits
    if _flag("SHADOWBOX_FINAL_TRANSFER") and bbest.version != 0:
        need = seconds_for_work(n_test)
        if BUDGET.fits(need):
            await optional_eval("test_transfer_vbest", bbest, llm, "transfer", limit)
            assemble(limit=limit)
        else:
            store.event("time_budget", f"Skipping transfer-after (needs ~{fmt(need)}, {fmt(BUDGET.left())} left)")
    if _flag("SHADOWBOX_FINAL_BREAKER_V0", default=False) and kbest.version != 0:  # optional extra, off by default
        if BUDGET.fits(sel_s):
            await selection("breaker_v0", drafts, n, "breaker", k0, llm)
        else:
            store.event("time_budget", f"Skipping Breaker-v0 selection (needs ~{fmt(sel_s)}, {fmt(BUDGET.left())} left)")
    if run_missing_baselines:  # standalone `final`: fill in comparisons that a cancelled or cut-short run never finished
        for flag, name, key in (("SHADOWBOX_FINAL_ULTRA", "test_ultra_v0", "ultra"), ("SHADOWBOX_FINAL_TRANSFER", "test_transfer_v0", "transfer")):
            if not _flag(flag) or _results(name, ids, b0, key) is not None:
                continue
            if not BUDGET.fits(seconds_for_work(n_test)):
                store.event("time_budget", f"Skipping {name} (not enough time left)")
                continue
            await optional_eval(name, b0, llm, key, limit)

    final = assemble(complete=True, limit=limit)
    m = final["metrics"]
    pct = lambda k: f"{m[k]['pass']:.0%}" if m.get(k) else "n/a"  # noqa: E731
    store.event("final_done", f"Held-out: v0 {pct('v0')} -> vBest {pct('vbest')} -> with Breaker {pct('vbest_selection')} "
                f"(random inputs {pct('random_input_sel')}, ceiling {pct('ceiling')})")
    store.update_state(status="finished", phase="done", step="done", message="Final exam complete")
    return final
