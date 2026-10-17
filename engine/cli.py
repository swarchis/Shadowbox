"""Command line entry point.

  python -m engine.cli check                   environment check (simulator, dataset, splits, key)
  python -m engine.cli smoke                   5 problems end to end; times real calls and projects a run
  python -m engine.cli run --minutes 60        everything: baselines + self-play (time-boxed) + final exam
  python -m engine.cli loop --rounds 3         self-play only
  python -m engine.cli final                   final exam only (uses the current best versions)
  python -m engine.cli ablation --rounds 3     Nano-coach ablation (Builder only, separate folder)
  python -m engine.cli compare --n 10          worker models side by side on training problems
  python -m engine.cli status                  print the run state
  python -m engine.cli reset-mock              delete runs_mock/ and versions_mock/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import signal
import sys
import time

from . import config, dataset, harness, playbook, store


def _banner():
    mode = "MOCK (no API key: fake model output, numbers are meaningless)" if config.MOCK else "REAL (Crusoe Managed Inference)"
    print(f"Shadowbox | mode: {mode}\n  runs: {config.RUNS_DIR}\n  versions: {config.VERSIONS_DIR}\n  spend cap: ${config.SPEND_CAP_USD:.2f}")


def cmd_check(_args) -> int:
    ok = True
    try:
        harness._bin("iverilog"), harness._bin("vvp")
        print(f"[ok] Icarus Verilog at {config.IVERILOG_BIN}")
    except harness.HarnessError as e:
        ok = False
        print(f"[!!] {e}")
    try:
        probs = dataset.load_problems()
        print(f"[ok] VerilogEval: {len(probs)} problems ({len(dataset.EXCLUDED)} excluded as broken)")
        s = dataset.load_splits()
        print(f"[ok] splits: train {len(s['train'])}, val {len(s['val'])}, test {len(s['test'])} (seed {s.get('seed')})")
        p = probs[s["train"][0]]
        r = harness.run_official(p, dataset.ref_source(p).replace("module RefModule", "module TopModule"))
        print(f"[{'ok' if r.passed else '!!'}] reference self-test on {p.id}: {r.kind}")
        ok &= r.passed
    except Exception as e:
        ok = False
        print(f"[!!] dataset: {e}")
    print(f"[{'ok' if config.CRUSOE_API_KEY else '--'}] CRUSOE_API_KEY {'set' if config.CRUSOE_API_KEY else 'not set (mock mode)'}")
    for k, m in config.MODELS.items():
        print(f"     model {k:8} = {m}  price/1M in,out = {config.PRICES.get(m, config.DEFAULT_PRICE)}")
    if not config.MOCK:
        print("Pinging every model with a tiny request (a fraction of a cent)...")
        ok &= asyncio.run(_ping_models())
    return 0 if ok else 1


async def _ping_models() -> bool:
    from .llm import FatalLLMError, LLMClient

    llm = LLMClient()
    all_ok = True
    try:  # /v1/models is free and is the source of truth for exact IDs (casing and prefixes vary)
        listed = {m.id: m for m in (await llm._client.models.list()).data}
        print(f"Crusoe lists {len(listed)} models for this key.")
        for key, mid in config.MODELS.items():
            if mid in listed:
                print(f"[ok] {key:8} {mid} is listed")
            else:
                near = [x for x in listed if x.lower() == mid.lower() or mid.split("/")[-1].lower() in x.lower()]
                print(f"[!!] {key:8} {mid} is NOT listed" + (f"; did you mean {near}? (set SHADOWBOX_{key.upper()}_MODEL)" if near else ""))
        if "nvidia" in config.MODELS["worker"].lower() and config.MODELS["worker"] in listed:
            params = getattr(listed[config.MODELS["worker"]], "supported_parameters", None)
            if params:
                print(f"     worker supported_parameters: {params}")
    except Exception as e:
        print(f"[??] could not list models: {type(e).__name__}: {str(e)[:200]}")
    for key in config.MODELS:
        try:
            r = await llm.chat(role="judge", model_key=key, max_tokens=64, tag=f"check:{key}",
                               messages=[{"role": "system", "content": "Reply with the single word OK."},
                                         {"role": "user", "content": "ping"}])
            print(f"[ok] {key:8} {config.MODELS[key]} answered in {r.latency_s:.1f}s")
        except FatalLLMError as e:
            all_ok = all_ok and key not in ("worker", "coach", "judge")  # ultra/transfer are optional comparisons
            print(f"[!!] {key:8} {config.MODELS[key]}: {e}")
        except Exception as e:
            print(f"[??] {key:8} {config.MODELS[key]}: {type(e).__name__}: {str(e)[:200]} (transient? try again)")
    print("Required: worker, coach, judge. Optional (skipped with a warning if broken): ultra, transfer.")
    return all_ok


async def _smoke(n: int) -> None:
    from .breaker import attack
    from .builder import build
    from .coach import propose
    from .llm import LEDGER, LLMClient

    playbook.ensure_v0()
    llm = LLMClient()
    b, k = playbook.load("builder", 0), playbook.load("breaker", 0)
    probs = dataset.split_problems("train", n)
    t0 = time.monotonic()
    spent0, calls0 = LEDGER.snapshot()

    async def one(p):
        r = await build(p, b, llm, tag="smoke")
        off = harness.run_official(p, r.code) if r.code else None
        a = await attack(p, r.code, k, llm, tag="smoke") if r.compiled else None
        bug = harness.check_against_ref(p, r.code, a.stimulus) if a and a.stimulus else None
        print(f"  {p.id:32} compiled={r.compiled!s:5} attempts={r.attempts} official={'PASS' if off and off.passed else (off.kind if off else 'no code'):9}"
              f" attack={'%d cycles' % len(a.stimulus) if a and a.stimulus else (a.error if a else '-')}"
              f" bug={'yes' if bug and bug.valid_bug else 'no'}{' ERROR ' + r.error if r.error else ''}")
        return r

    print(f"Building and attacking {n} training problems with v0 playbooks...")
    await asyncio.gather(*(one(p) for p in probs))
    t_work = time.monotonic() - t0
    fake_match = {"problems": []}
    t1 = time.monotonic()
    props, _, _ = await propose("builder", b, fake_match, llm, k=1, round_no=0)
    t_coach = time.monotonic() - t1
    spent1, calls1 = LEDGER.snapshot()
    rows = store.read_jsonl(store.ledger_path())[calls0:]
    lat = [r["latency_s"] for r in rows]
    print(f"\n{calls1 - calls0} LLM calls, ${spent1 - spent0:.4f}, wall {t_work:.1f}s for {n} problems "
          f"(concurrency {config.LLM_CONCURRENCY}), coach call {t_coach:.1f}s, coach proposals parsed: {len(props)}")
    if lat:
        print(f"call latency: median {sorted(lat)[len(lat) // 2]:.1f}s, max {max(lat):.1f}s")
    s = dataset.load_splits()
    per_problem_s = t_work * min(n, config.LLM_CONCURRENCY) / n
    per_problem_cost = (spent1 - spent0) / n
    round_items = len(s["train"]) + len(s["val"]) * config.CANDIDATES_PER_ROUND + config.BUG_POOL_MAX * config.CANDIDATES_PER_ROUND * 0.4
    round_s = round_items * per_problem_s / config.LLM_CONCURRENCY + 2 * t_coach
    final_items = len(s["test"]) * (2 + config.TEST_TIME_DRAFTS) + len(s["test"]) * 0.5
    final_s = final_items * per_problem_s / config.LLM_CONCURRENCY
    setup_s = len(s["val"]) * (1 + config.BUG_POOL_EXTRA_DRAFTS) * per_problem_s / config.LLM_CONCURRENCY
    print(f"\nProjection (rough): setup ~{setup_s / 60:.1f} min, one round ~{round_s / 60:.1f} min / ~${round_items * per_problem_cost:.2f}, "
          f"final exam ~{final_s / 60:.1f} min / ~${final_items * per_problem_cost:.2f}")
    for minutes in (45, 60, 90):
        fit = max(0, int((minutes * 60 - setup_s - final_s) // max(round_s, 1)))
        print(f"  {minutes} min budget -> about {fit} round(s)")
    print("Raise SHADOWBOX_CONCURRENCY if Crusoe's rate limits allow; it scales almost linearly.")


async def _run(args) -> None:
    """Baselines + self-play + final exam, inside one time budget with a hard stop at deadline + grace."""
    from . import budget, final_eval, loop
    from .llm import LLMClient

    B = budget.set_budget(args.minutes, grace_minutes=args.grace)
    llm = LLMClient()
    side = LLMClient(concurrency=config.BASELINE_CONCURRENCY)  # baselines' own lane: never starve self-play
    playbook.ensure_v0()
    b0 = playbook.load("builder", 0)
    # Runs that don't depend on the loop start now and share the model concurrency with it.
    required = asyncio.create_task(final_eval.eval_test("test_v0", b0, side))
    optional = []
    if final_eval._flag("SHADOWBOX_FINAL_ULTRA"):
        optional.append(asyncio.create_task(final_eval.optional_eval("test_ultra_v0", b0, side, "ultra", None)))
    if final_eval._flag("SHADOWBOX_FINAL_TRANSFER"):
        optional.append(asyncio.create_task(final_eval.optional_eval("test_transfer_v0", b0, side, "transfer", None)))
    tasks = [required, *optional]
    try:
        async with asyncio.timeout(None if not B.enabled else B.hard_left()):
            await loop.run_loop(rounds=args.rounds, minutes=None, k=args.k, reserve_final=not args.no_final, llm=llm)
            await required
            if not args.no_final:
                pending = [t for t in optional if not t.done()]
                if pending and B.enabled:
                    n_test = len(dataset.load_splits()["test"])
                    need = budget.seconds_for_work(budget.final_work(n_test, final_eval.DRAFT_MIN))
                    if not B.fits(need * 1.3):
                        for t in pending:
                            t.cancel()
                        store.event("time_budget", f"Cancelled {len(pending)} optional baseline(s) (Ultra / transfer-before) to protect the final exam")
                await final_eval.run_final(llm, run_missing_baselines=False)  # the optional baselines are running as tasks here
            for res in await asyncio.gather(*optional, return_exceptions=True):
                if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
                    store.event("optional_failed", f"An optional comparison (Ultra / transfer-before) failed: {type(res).__name__}: {str(res)[:200]}")
            final_eval.assemble(complete=not args.no_final)
            if args.no_final:
                store.update_state(status="finished", phase="round", step="done", message="Self-play finished (final exam skipped)")
    except TimeoutError:
        store.event("hard_stop", f"Hard stop: the {args.minutes:.0f}-minute budget plus {args.grace:g} min grace ran out")
        final = final_eval.assemble(complete=False, note="Stopped at the time limit; these are the results that finished. "
                                                         "Rerun `python -m engine.cli final` to complete the rest from cache.")
        store.update_state(status="finished", phase="done", step="done", message="Stopped at the time limit; partial final results shown")
        print(f"\nHARD STOP at the time limit. Partial results saved ({sum(v is not None for v in final['metrics'].values())} metrics).", file=sys.stderr)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _ablation(args) -> None:
    """Same self-play as the main run (both teams, same splits, same frozen bug pool, same K), changing
    ONE thing: both coaches use the worker model. Runs in its own folder; spending counts against the
    main run's ledger and cap."""
    import shutil as _sh

    from . import gatekeeper, loop
    from .llm import LLMClient

    main_runs, main_versions = config.RUNS_DIR, config.VERSIONS_DIR
    sub = main_runs / "ablation_nano_coach"
    config.LEDGER_PATH = main_runs / "ledger.jsonl"
    for f in ("bug_pool.json", "cache/builder_0_val.json", "cache/breaker_0_pool.json"):  # reuse, don't pay twice
        if (main_runs / f).exists() and not (sub / f).exists():
            (sub / f).parent.mkdir(parents=True, exist_ok=True)
            _sh.copy(main_runs / f, sub / f)
    config.RUNS_DIR, config.VERSIONS_DIR = sub, sub / "versions"
    try:
        ctx = await loop.run_loop(rounds=args.rounds, minutes=None, k=args.k, coach_model="worker", llm=LLMClient())
        v0 = store.read_json(gatekeeper.cache_path("builder_0_val"))["results"]
        cur = store.read_json(gatekeeper.cache_path(f"builder_{playbook.current_version('builder')}_val"))["results"]
        nano_gain = gatekeeper.score(cur, "passed") - gatekeeper.score(v0, "passed")
    finally:
        config.RUNS_DIR, config.VERSIONS_DIR, config.LEDGER_PATH = main_runs, main_versions, None
    series = store.read_json(main_runs / "series.json", {}) or {}
    pts = {p["round"]: p for p in series.get("points", [])}
    main_gain = None
    if 0 in pts and args.rounds in pts and pts[0]["builder_val_pass"] is not None and pts[args.rounds]["builder_val_pass"] is not None:
        main_gain = pts[args.rounds]["builder_val_pass"] - pts[0]["builder_val_pass"]
    res = {"rounds": args.rounds, "val_problems": len(ctx.val), "nano_gain": round(nano_gain, 4),
           "main_gain": round(main_gain, 4) if main_gain is not None else None,
           "note": f"Gain in Builder validation pass rate after {args.rounds} rounds; identical settings except the coach model."}
    store.write_json(main_runs / "ablation_nano_coach" / "result.json", res)
    if main_gain is None:
        print(f"note: the main run has fewer than {args.rounds} rounds, so there is no main-coach gain to compare yet")
    print(json.dumps(res, indent=2))


async def _compare(args) -> None:
    """Build the same training problems with each candidate worker model (v0 playbook, temperature 0)
    and compare pass rate, compile rate, speed and cost. Uses train problems only."""
    from . import gatekeeper
    from .llm import LLMClient

    playbook.ensure_v0()
    pb = playbook.load("builder", 0)
    probs = dataset.split_problems("train", args.n)
    llm = LLMClient()
    print(f"Comparing {len(args.models)} worker model(s) on {len(probs)} training problems (v0 playbook)...")
    rows = []
    for model in args.models:
        n0 = len(store.read_jsonl(store.ledger_path()))
        t0 = time.monotonic()
        res = await gatekeeper.run_builder_on(probs, pb, llm, tag=f"compare:{model}", model_key=model)
        wall = time.monotonic() - t0
        calls = store.read_jsonl(store.ledger_path())[n0:]
        rows.append((model, sum(r["passed"] for r in res.values()), sum(bool(r["compiled"]) for r in res.values()),
                     sum(bool(r.get("error")) for r in res.values()), wall, sum(c["cost_usd"] for c in calls),
                     sum(c["output_tokens"] for c in calls) / max(1, len(calls)), len(calls)))
    print(f"\n{'model':45} {'pass':>6} {'compiled':>9} {'errors':>7} {'wall':>7} {'cost':>8} {'out tok/call':>13} {'calls':>6}")
    for m, ok, comp, err, wall, cost, tok, calls in rows:
        print(f"{m:45} {ok:>3}/{len(probs):<2} {comp:>6}/{len(probs):<2} {err:>7} {wall:>6.0f}s ${cost:>7.4f} {tok:>13.0f} {calls:>6}")
    print("\nPick the worker with the best pass rate (it also needs headroom to improve); set SHADOWBOX_WORKER_MODEL in .env.")


def cmd_status(_args) -> int:
    which = store.select_run_dirs()
    print(f"(showing the {which} run in {config.RUNS_DIR}; set SHADOWBOX_DATA=real|mock to choose)")
    st = store.read_state()
    print(json.dumps(st, indent=2))
    series = store.read_json(store.runs_dir() / "series.json", {}) or {}
    for p in series.get("points", []):
        print(f"  round {p['round']}: builder val {p['builder_val_pass']}, breaker pool {p['breaker_pool_catch']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.cli", description="Shadowbox self-play engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sp = sub.add_parser("smoke")
    sp.add_argument("--n", type=int, default=5)
    for name in ("run", "loop"):
        p = sub.add_parser(name)
        p.add_argument("--minutes", type=float, default=None, help="time budget; stops starting rounds when it would overrun")
        p.add_argument("--rounds", type=int, default=None, help="maximum number of rounds")
        p.add_argument("--k", type=int, default=config.CANDIDATES_PER_ROUND, help="candidates per coach per round")
        if name == "run":
            p.add_argument("--no-final", action="store_true")
            p.add_argument("--grace", type=float, default=5.0, help="minutes past --minutes before the hard stop (default 5)")
    fp = sub.add_parser("final")
    fp.add_argument("--limit", type=int, default=None, help="only the first N held-out problems (testing)")
    fp.add_argument("--drafts", type=int, default=None)
    ab = sub.add_parser("ablation")
    ab.add_argument("--rounds", type=int, default=3)
    ab.add_argument("--k", type=int, default=config.CANDIDATES_PER_ROUND)
    cp = sub.add_parser("compare")
    cp.add_argument("--n", type=int, default=10)
    cp.add_argument("--models", nargs="+", default=["nvidia/Nemotron-3.5-Lightning-30B-A3B", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"])
    sub.add_parser("status")
    sub.add_parser("reset-mock")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        _banner()
        return cmd_check(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "reset-mock":
        for d in (config.ROOT / "runs_mock", config.ROOT / "versions_mock"):
            shutil.rmtree(d, ignore_errors=True)
        print("mock folders removed")
        return 0
    _banner()
    if args.cmd in ("run", "loop") and args.rounds is None and args.minutes is None:
        print("error: pass --minutes and/or --rounds", file=sys.stderr)
        return 2
    from .llm import FatalLLMError, SpendCapExceeded

    def _stop(signum, _frame):  # `kill <pid>` or closing the terminal: stop like Ctrl-C (state saved, resumable)
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _stop)
    try:
        if args.cmd == "smoke":
            asyncio.run(_smoke(args.n))
        elif args.cmd == "run":
            asyncio.run(_run(args))
        elif args.cmd == "loop":
            from . import loop

            asyncio.run(loop.run_loop(rounds=args.rounds, minutes=args.minutes, k=args.k))
            store.update_state(status="finished", phase="round", step="done", message="Self-play finished (no final exam run)")
        elif args.cmd == "final":
            from . import final_eval

            asyncio.run(final_eval.run_final(limit=args.limit, n_drafts=args.drafts))
        elif args.cmd == "ablation":
            asyncio.run(_ablation(args))
        elif args.cmd == "compare":
            asyncio.run(_compare(args))
    except SpendCapExceeded as e:
        store.update_state(status="stopped", message=f"Stopped at the spend cap: {e}")
        print(f"\nSTOPPED: {e}. Everything so far is saved; raise SHADOWBOX_SPEND_CAP and rerun to resume.", file=sys.stderr)
        return 3
    except FatalLLMError as e:
        store.update_state(status="error", message=f"Stopped: {e}")
        store.event("fatal", str(e))
        print(f"\nSTOPPED (fix this, then rerun the same command to resume): {e}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        store.update_state(status="stopped", message="Interrupted; rerun the same command to resume")
        print("\nInterrupted. Rerun the same command to resume from the last checkpoint.", file=sys.stderr)
        return 130
    except Exception as e:
        store.update_state(status="error", message=f"Crashed: {type(e).__name__}: {e}"[:300])
        store.event("crash", f"{type(e).__name__}: {e}"[:300])
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
