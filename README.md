# Shadowbox

**Self-play agent teams that teach each other chip design.**

Two AI teams work on English hardware specs from NVIDIA's VerilogEval benchmark:

- The **Builder** team writes Verilog that implements the spec.
- The **Breaker** team writes input sequences that try to expose bugs in the Builder's designs.

After every round, each team's **coach** reads the results and proposes a change to its own team's **playbook**: a prompt, a rule, a Python checking tool, or a setting. A **gatekeeper** tests each change on separate data and keeps it only if it measurably helps. The model weights never change. Only the team around the model rewrites itself.

At test time the two teams work together. The Builder writes several drafts, the Breaker searches for inputs where the drafts disagree, and the majority behavior wins. No answer key is needed.

Built at the Recursive Agents Hackathon (Cerebral Valley x Crusoe), Version N+1 track. Every LLM call goes through Crusoe Managed Inference.

| Doc | What's in it |
|---|---|
| [PRD.md](PRD.md) | Product spec, design decisions, hackathon rules |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | The 1-minute demo video script |
| [docs/CONTRACT.md](docs/CONTRACT.md) | Exact JSON shapes shared by the engine, the API and the UI |

---

## Contents

1. [Quick start](#quick-start)
2. [Running it for real](#running-it-for-real)
3. [Mock mode, tests and UI development](#mock-mode-tests-and-ui-development)
4. [Architecture in depth](#architecture-in-depth)
5. [Configuration reference](#configuration-reference)
6. [Output layout](#output-layout)
7. [Results from earlier runs](#results-from-earlier-runs)
8. [Repository layout](#repository-layout)

---

## Quick start

### On this machine (already set up)

This folder already has a Python virtualenv in `.venv/` (Python 3.12 with openai, fastapi, uvicorn, pytest and httpx), Icarus Verilog 12 built into `.tools/iv/`, the VerilogEval dataset in `data/raw/verilog-eval/`, and a built UI in `web/dist/`.

```bash
cd ~/Downloads/Shadowbox_NVIDIA_RAH
```

Put your Crusoe key in `.env` as `CRUSOE_API_KEY=...`. If `.env` doesn't exist yet, start from the example. `.env` is git-ignored, and real environment variables override it.

```bash
cp .env.example .env
```

Check the environment. This verifies the simulator, the dataset, the locked splits and a reference self-test, then pings every configured model:

```bash
.venv/bin/python -m engine.cli check
```

Run everything (baselines, self-play, final exam) in a 60-minute budget:

```bash
.venv/bin/python -m engine.cli run --minutes 60
```

Watch it live from a second terminal, then open http://127.0.0.1:8000:

```bash
.venv/bin/python -m server.api
```

With no API key, all of this runs against an offline mock model instead (see [Mock mode](#mock-mode-no-api-key)).

### From scratch on another machine

Requirements: Python 3.11+ (the code uses `asyncio.timeout`), Icarus Verilog 12 (`iverilog` and `vvp`), Node 18+ for the UI, and macOS for the full tool sandbox (see [Coach-written tools](#coach-written-tools-and-the-sandbox-enginetools_runnerpy)).

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install openai fastapi "uvicorn[standard]" pytest httpx
```

Install Icarus Verilog 12 so `iverilog` is on your PATH (for example with Homebrew's `icarus-verilog` or your distro's package). The engine looks in `.tools/iv/bin/` first, then on PATH.

Download VerilogEval (MIT license, NVIDIA). It is downloaded, not committed:

```bash
git clone --depth 1 https://github.com/NVlabs/verilog-eval.git data/raw/verilog-eval
```

Build the UI:

```bash
npm --prefix web install
```

```bash
npm --prefix web run build
```

`data/splits.json` is committed, so every machine uses the same train, validation and held-out split.

---

## Running it for real

The hackathon-day checklist.

### 1. Key and models

Set the key (in `.env` or the shell), then run `check`. It lists the models Crusoe offers your key, confirms each configured ID is among them (and suggests the right spelling if not), sends each model a tiny ping, and prints the assumed price. Compare those with the Crusoe console.

```bash
.venv/bin/python -m engine.cli check
```

Override any model with `SHADOWBOX_WORKER_MODEL`, `SHADOWBOX_COACH_MODEL`, `SHADOWBOX_JUDGE_MODEL`, `SHADOWBOX_ULTRA_MODEL` or `SHADOWBOX_TRANSFER_MODEL`, or edit `engine/config.py`. Worker, coach and judge are required. Ultra and transfer are optional comparisons: if their IDs are wrong, the run skips them with a warning.

### 2. Smoke test

Five training problems end to end (about 2 minutes, a few cents). Prints per-problem results, call latency, cost, and a projection of how many rounds fit in 45, 60 and 90 minutes.

```bash
.venv/bin/python -m engine.cli smoke
```

If calls fail or every design fails to compile, stop and read the output before going further.

Optional: compare worker models on the same training problems (pass rate, compile rate, speed, cost). On hackathon day, Nemotron 3.5 Lightning beat Nemotron 3 Nano 16/30 to 13/30, and was faster and cheaper.

```bash
.venv/bin/python -m engine.cli compare --n 30
```

### 3. Full run

```bash
.venv/bin/python -m engine.cli run --minutes 60
```

How the time budget works:

- The run measures real throughput (finished builds and attacks per second) as it goes.
- It starts another round only if that round **plus** the required final exam still fit before the deadline.
- The final exam is incremental. v0, the latest version, and 3 drafts per problem are required. Drafts 4–5 and the optional comparisons run only if they fit. Results are saved after every step.
- **Hard stop** at `--minutes` + `--grace` (default 5 minutes). Anything still running is cancelled, and the Final Exam view shows every number that finished. Use `--grace 0` for a strict cut-off. Run `final` later to complete the rest from cache.

Other flags: `--rounds N` caps the number of rounds, `--k N` sets proposals per coach per round, and `--no-final` skips the final exam.

Safe to stop and rerun:

- Every step is checkpointed, and finished builds are saved as they complete. An interruption (Ctrl-C, closing the terminal, `kill`) never re-bills finished work.
- Rerunning the same command resumes where it left off.
- Each manual restart is counted in the UI as a "human intervention".
- The run stops cleanly at the spend cap (`SHADOWBOX_SPEND_CAP`, default $45). Raise it and rerun to continue.

### 4. Watch it live

```bash
.venv/bin/python -m server.api
```

Open http://127.0.0.1:8000. The server serves the built UI from `web/dist/` and the REST API under `/api/` (interactive API docs at `/api/docs`).

- **Which run it shows:** the real run in `runs/` if one exists, otherwise the mock run. This doesn't depend on whether that terminal has the key. Force one with `SHADOWBOX_DATA=real` or `SHADOWBOX_DATA=mock`. A **MOCK DATA** badge appears whenever the data comes from mock mode.
- **If the API goes down:** the UI keeps the last real data, shows an **API OFFLINE** badge, and keeps retrying. It never substitutes sample numbers. Sample data appears only with `?fixtures=1`, under a **FIXTURE DATA** badge.

### 5. Other commands

All of these run as `.venv/bin/python -m engine.cli <command>`.

| Command | What it does |
|---|---|
| `loop --rounds 3` | Self-play only, no final exam |
| `final` | Final exam only, with the current versions. Also fills in comparisons a cut-short run never finished |
| `ablation --rounds 3` | The same self-play with the worker model as both coaches, in `runs/ablation_nano_coach/`. Rerun `final` afterwards to show it in the Final Exam view |
| `status` | Print the run state and per-round scores |
| `reset-mock` | Delete `runs_mock/` and `versions_mock/` |

### Demo mode (the 1-minute video)

- **Start it:** press **D** (or click **Demo**) at http://127.0.0.1:8000, or open http://127.0.0.1:8000/?demo=1.
- **Scenes:** 6 scenes on a 60-second timeline that follows [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
- **Keys:** →/Space next, ← back, **P** pause, **R** restart, **F** fullscreen, **Esc** exit, **1–6** jump to a scene.
- **Team names, photos and repo URL** come from [demo.json](demo.json), which still holds placeholder values. Edit it before recording. For photos, put images in `web/public/team/`, set `"photo": "team/<file>.jpg"`, then rebuild with `npm --prefix web run build`.
- **Rehearse one moment:** `?demo=1&scene=4&at=6.5&paused=1` opens scene 4 paused at 6.5 s.
- **Claims follow the data:** the transfer card appears only if the learned playbook improves the other model by at least 2 points, and the "beats the big model" headline appears only when it's true.

---

## Mock mode, tests and UI development

### Mock mode (no API key)

With no `CRUSOE_API_KEY` (or with `SHADOWBOX_MOCK=1`), every model call goes to `engine/mock_llm.py`, an offline stand-in that produces well-formed but fake output. It exercises every code path (parsing, simulation, gating, checkpoints, UI) for free. Its numbers mean nothing.

The mock cheats on purpose: it reads the reference design and sometimes injects a bug, and its canned coach proposals have built-in good or bad effects, so the gate sees a mix of accepts and rejects. That's acceptable only because the mock module is never loaded in real mode. Mock output goes to `runs_mock/` and `versions_mock/`, never `runs/`.

```bash
.venv/bin/python -m engine.cli run --rounds 3
```

```bash
.venv/bin/python -m engine.cli reset-mock
```

### Tests

```bash
.venv/bin/python -m pytest -q
```

229 tests (some parametrized) in four files. They always run offline: `tests/conftest.py` stops `.env` from loading and removes any key from the environment.

| File | Covers |
|---|---|
| `tests/test_engine.py` | Port parsing, splits, official grading of every reference, compile checks, stimulus rules, reference and draft comparisons, tool screen and sandbox, proposal validation, gate math, output parsing, storage, a full mini mock loop and its no-op rerun |
| `tests/test_api.py` | Every endpoint against the contract, partial and corrupt files, path-traversal guards |
| `tests/test_llm_real.py` | The real Crusoe client path with a faked API: seeds, truncation retries, fatal errors, rate-limit retries, rate throttle, reasoning control, spend cap, cache reruns |
| `tests/test_review_fixes.py` | Regression tests for bugs found in code review |

### UI development

Run the API on port 8000 as above, then the Vite dev server, which proxies `/api` to port 8000:

```bash
npm --prefix web run dev
```

After changing UI code, rebuild so the API server serves the new version:

```bash
npm --prefix web run build
```

`.claude/launch.json` defines both servers (`shadowbox` on 8000, `web-dev` on 5173) for the Claude desktop app's preview.

---

## Architecture in depth

### The big picture

```
                    VerilogEval v2 (152 usable problems)
                    split once, locked in data/splits.json
          ┌──────────────────┬──────────────────┬────────────────────┐
          │ train (30)       │ validation (30)  │ held-out test (92) │
          │ rounds are       │ Builder changes  │ final exam only;   │
          │ played here      │ are gated here   │ no agent sees it   │
          └────────┬─────────┴────────┬─────────┴──────────┬─────────┘
                   │                  │                    │
                   ▼                  ▼                    ▼
 ┌─ ROUND n ───────────────────────────────────────────┐ ┌─ FINAL EXAM ──────────────┐
 │ 1. MATCH (train)                                    │ │ v0 vs latest version      │
 │    Builder writes ──► harness compiles + grades     │ │ + 5 drafts per problem    │
 │    Breaker attacks ─► harness checks vs reference   │ │ + Breaker picks a draft   │
 │                                                     │ │ + comparisons (random,    │
 │ 2. BUILDER COACH reads failures ─► proposals        │ │   ceiling, big model,     │
 │    GATE: candidate vs current on validation         │ │   other model)            │
 │                                                     │ └───────────────────────────┘
 │ 3. BREAKER COACH reads hits/misses ─► proposals     │
 │    GATE: candidate vs current on frozen bug pool    │
 │                                                     │
 │ accepted change ─► new playbook version (v1, v2...) │
 └─────────────────────────────────────────────────────┘
          │
          ▼
   runs/ + versions/ (plain JSON) ──► server/api.py (read-only) ──► web/ (React, polls)
```

Every LLM call, from every component, goes through one client (`engine/llm.py`). It talks to Crusoe's OpenAI-compatible endpoint, logs cost to a ledger, retries transient failures, and enforces the spend cap.

### Technology used

| Layer | Technology | Role |
|---|---|---|
| Models | **Crusoe Managed Inference** (OpenAI-compatible API) | Hosts every model the agents use |
| Worker model | `nvidia/Nemotron-3.5-Lightning-30B-A3B` | Builder (planner, writer, debugger) and Breaker (attacker). Small and cheap on purpose, so there's headroom to improve |
| Coach model | `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B` | Both coaches, with low-effort reasoning |
| Judge model | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Breaks ties during test-time selection. Using a different model than the worker also spreads per-model rate limits |
| Comparison models | Nemotron 3 Super 120B (stand-in for "Ultra", which this key can't access), `google/gemma-4-31b-it` ("transfer") | Big-model baseline and transfer check in the final exam |
| Engine | Python 3.11+, `asyncio`, `openai` SDK | Plain Python, no agent framework |
| Simulator | **Icarus Verilog 12** (`iverilog` + `vvp`) | Compiles and simulates every design, with VerilogEval's own flags (`-Wall -Winfloop -Wno-timescale -g2012`) |
| Benchmark | **VerilogEval v2** spec-to-RTL (NVIDIA, MIT) | Specs, reference designs, official testbenches |
| Sandbox | macOS `sandbox-exec` plus an isolated Python subprocess | Runs coach-written tools |
| API | **FastAPI** + **uvicorn** | Read-only REST over the engine's files; also serves the built UI |
| UI | **React 18**, **Vite 5**, **TypeScript**, **Tailwind 3**, **Recharts**, **Framer Motion**, lucide-react, Inter and JetBrains Mono | Dashboard and demo mode |
| Storage | Plain JSON and JSONL files | No database. Every write is atomic (temp file, then rename) |
| Tests | pytest, httpx (FastAPI's TestClient) | Offline test suite |

### Data and splits (`engine/dataset.py`)

- **Source:** VerilogEval v2 spec-to-RTL, 156 problems. Each has `<id>_prompt.txt` (the English spec, the only thing agents may read), `<id>_ref.sv` (the reference design, module `RefModule`), and `<id>_test.sv` (the official testbench).
- **Exclusions:** 4 problems are dropped because even their own reference fails official grading. Three hit the testbench's 1,000,000 ps limit, and one testbench connects ports the reference doesn't declare. That leaves 152.
- **Port parsing:** a small parser reads each reference's ANSI port list (type keywords, parameterized ranges like `[W-1:0]`, initializers) to get names, directions and widths. A problem with a `clk` or `clock` input counts as sequential.
- **Splits:** 30 train, 30 validation, 92 held-out, stratified so each split has the same mix of combinational and sequential problems. Seed 1234. Chosen once and locked in `data/splits.json`.

### The harness (`engine/harness.py`)

The harness is the only code that touches reference designs and official testbenches. It has four jobs.

1. **Compile check** (`compile_check`). Compiles a candidate on its own and checks its interface: a `TopModule` must exist, and its ports must match the spec's names, directions and widths. Uses nothing from the reference. This is the feedback the Builder is allowed to see.
2. **Official grading** (`run_official`). Compiles the candidate with VerilogEval's testbench and reference, runs it, and applies the official pass rule (`Mismatches: 0`). Results are classified as `pass`, `syntax`, `compile`, `bind`, `timeout`, `mismatch` or `no_result`. Used only for scoring and for coaches, never fed back to a Builder still working on that problem.
3. **Stimulus-driven simulation** (`simulate`). Generates a testbench from a JSON stimulus (one object of input values per cycle), drives each design in its own simulator process, and records the outputs. Clocked designs are sampled before and after each rising edge. Inputs left out of a cycle hold their previous value. Values may be decimal, `"0x.."`, `"0b.."` or Verilog-style literals. At most 200 cycles.
4. **Two kinds of comparison**, built on that simulation:
   - `check_against_ref` (**training only**): the Builder's design vs the reference, on the Breaker's stimulus. Any mismatch is a guaranteed real bug. As in the official rule, an X or Z bit in the reference matches anything. A design that fails to simulate is reported as an error, never as a bug.
   - `group_by_behavior` (**test time**, no reference): simulate several drafts on the same stimulus and group the ones with identical outputs. Bit positions where every draft is X are ignored, but a draft stuck at X where others drive 0 or 1 counts as different.

### The Builder team (`engine/builder.py`)

```
spec ─► [planner] ─► writer ─► compile check + toolbox ─┬─ clean ─► done
         optional               ▲                       │
                                └──── debugger ◄────────┘  (up to max_debug_attempts)
```

- **Planner** (off in v0): writes a design outline before any code.
- **Writer:** writes the full `TopModule` in a ```verilog block.
- **Check:** compile check plus every tool in the team's toolbox. If the design compiles and no tool fires, it's done.
- **Debugger:** gets the spec, its code, compiler errors and warnings, and tool findings, and returns a fixed module. Repeats up to `max_debug_attempts` times (2 in v0).
- **Team drafting** (`drafts` param, 1 in v0): if a coach raises it to N, the team writes N drafts at temperature 0.7 and uses the test-time selector (below) to pick one. It's a team-structure change the loop can make to itself.
- **What the Builder sees:** the spec, its own code, compiler output and its own tools' findings. Never the reference, the testbench or official results.

### The Breaker team (`engine/breaker.py`)

- **Attacker** (training): reads the spec, the port list and one Builder design, and returns a JSON stimulus meant to make the design misbehave. The harness then checks it against the hidden reference. Only a confirmed mismatch counts as a found bug.
- **Multi-attacker** (test time): reads several drafts at once and looks for inputs where they'll disagree.
- **Robustness:** unquoted hex and Verilog literals in the JSON are quoted automatically. Malformed output gets one repair turn with the error message. The stimulus is cut to the playbook's `max_cycles` (40 in v0). Designs with no inputs get 4 idle cycles.
- **Tools:** the Breaker's toolbox runs on the design before attacking, and its findings are shown to the attacker as hints.

### Playbooks and versions (`engine/playbook.py`, `engine/prompts.py`)

A playbook is everything a team can learn:

```json
{
  "team": "builder", "version": 2, "parent": 1, "created_round": 3,
  "prompts": {"planner": "...", "writer": "...", "debugger": "..."},
  "rules":   ["If the specification says the reset is asynchronous, ..."],
  "tools":   ["always_output_logic_check"],
  "params":  {"max_debug_attempts": 2, "use_planner": false, "think": "off", "drafts": 1}
}
```

- **v0** comes from `engine/prompts.py`. Its prompts are deliberately plain and correct, not tuned, so every improvement has to come from the loop.
- **Rules** are appended to every system prompt as a numbered list.
- **Versions** are folders: `versions/<team>/v<n>/playbook.json` plus `tools/<name>.py`. `current.json` points at the active version. Each version is written to a temp folder and renamed into place, so a crash never leaves half a version.
- **Fingerprint:** a hash of a playbook's content (prompts, rules, tools, tool code, params). Every result cache is keyed on it, so changing a playbook automatically invalidates stale results.
- **Lineage** (`versions/lineage.json`): every proposal ever made, accepted or not, with the coach's reasoning, the problems it fixed and broke, scores before and after, and cost. The coaches read their own history from it so they don't repeat rejected ideas.

### Coaches (`engine/coach.py`)

After each match, each coach gets a report and proposes K changes (default 1).

- **Builder coach report:** for every failed training problem, the spec, the code, and why it failed (compile errors, the official result and hints, any bug the Breaker exposed with the exact cycle and signal, tools that fired). Plus a few short **passing** designs, so it can see what must not change.
- **Breaker coach report:** which attacks exposed a real bug, and which buggy designs were missed (with the hidden official hints for those misses).
- **Change types:** `rule_add`, `rule_remove`, `prompt_edit`, `tool_add`, `tool_remove`, `param`. Builder params: `max_debug_attempts` (1–3), `use_planner`, `think` (`off`, `low`, `on`), `drafts` (1–5). Breaker param: `max_cycles` (8–200).
- **Lessons from earlier runs are built into the coach prompt:** broad style rules break designs that already pass, so prefer conditional rules and tools (a tool only acts when it fires, so it can't break a correct design).
- **Validation before anything is spent** (`apply`): unknown change types, duplicate rules, bad indexes, out-of-range params, Breaker prompts that drop the JSON format, and tools that fail the guards below are rejected and logged without evaluation.
- **Settings sweep** (in `loop.py`): each round, the Builder also tries one untried setting from a fixed list (`think=low`, `drafts=3`, `use_planner=true`, `think=on`). It's gated like any coach proposal and marked `source: "sweep"` in the lineage.
- With `--k 3` or more, a coach must propose one rule change, one tool change and one param change, to force exploration.

### Coach-written tools and the sandbox (`engine/tools_runner.py`)

A tool is a Python file defining `run(spec, verilog, ports)` that returns `{"fired": bool, "findings": [str]}`. When a Builder tool fires, the draft goes back to the debugger with the findings. Breaker tools give the attacker hints.

Guards before a tool can join a toolbox:

- At least **3** different failing problems must be cited as evidence.
- **Static screen:** only standard-library imports from an allowlist (`re`, `math`, `itertools`, `collections`, `string`, `functools`, `dataclasses`, `typing`, `json`, `textwrap`). No `open`, `eval`, `exec`, `getattr`, dunder names, or references to `os`, `sys`, `subprocess` and similar. At most 150 lines. No hardcoded problem IDs.
- It must not crash on a one-bit-inverter smoke test.
- At most **6** tools per toolbox.

Each tool run is a separate `python -I -S` process with an empty environment, a temp working directory and a 10-second timeout. On macOS it also runs under `sandbox-exec`, with a profile that denies network access, denies writes outside the temp directory, and denies reads of the project folder (references, held-out data, results) and your home folder. On Linux only the static screen and the timeout apply. Per-tool stats (runs, times fired, errors, round added) go to `versions/<team>/tool_stats.json`.

### The gatekeeper (`engine/gatekeeper.py`)

Every candidate is compared to the current version **on the same items** (a paired comparison):

- **Builder candidates** run on the 30 validation problems, graded by the official testbenches.
- **Breaker candidates** run on the frozen bug pool. "Caught" means the reference confirms a real mismatch.

The best candidate (most net flips, then fewest losses) is accepted if either:

- **net flips ≥ 3** (problems newly passing minus problems newly failing), or
- it's a **clean win**: it fixes at least 2 and breaks none.

Items that hit an API error on either side are skipped, never counted as wrong. If more than 3 items errored, the comparison isn't trusted and nothing is accepted. Because a change is only accepted when it beats the current version, the current version is always the best one so far.

### The frozen bug pool (`engine/bug_pool.py`)

If the Breaker were scored on the current Builder's bugs, its score would drop whenever the Builder improved. So the Breaker is scored on a fixed target instead.

- **Sources:** Builder v0's validation designs (temperature 0) plus 2 extra drafts per problem at temperature 0.7.
- **Kept:** designs that compile but fail the official testbench, deduplicated by code hash, picked round-robin across problems for diversity, up to 50.
- **Difficulty baseline:** each entry is also tried against 40 random cycles (`caught_by_random40`).
- **Frozen** in `runs/bug_pool.json` once every source build succeeded. If any source build hit an API error, the pool is used for that session only and rebuilt on the next run.

### The hard suite

During matches, every stimulus that exposed a real bug is saved per problem in `runs/hard_suite.json` (up to 5 per problem). A training design "hard passes" only if it passes the official testbench **and** every saved Breaker stimulus for that problem. This catches subtle bugs the official tests miss; they're counted as `subtle_bugs` in the match summary.

### The self-play loop (`engine/loop.py`)

**Setup (once):**

1. Write the v0 playbooks.
2. Score Builder v0 on validation (`runs/baseline/val_v0.json`).
3. Build the frozen bug pool from v0's mistakes.
4. Score Breaker v0 on the pool.

**Each round n:**

1. **Match** on the 30 training problems. The current Builder builds each one and it's officially graded. The current Breaker attacks each design that compiled, and each attack is checked against the reference. The hard suite grows. Unchanged temperature-0 builds from the previous round are reused. Saved as `runs/round_<n>/match.json`.
2. **Builder gate.** The coach proposes (proposals are saved before any evaluation, so a crash never re-bills the coach). The settings sweep adds one more. Candidates are validated, saved under `versions/builder/candidates/`, and evaluated on validation. The winner, if any, is promoted to the next version.
3. **Breaker gate.** The same, on the bug pool.
4. Write `done.json`, update `series.json` (the arms-race chart data), and emit events.

**Resume:** every step checks for its own output file first. A rerun skips completed rounds, reuses saved proposals, and always gates against the version the proposals were written for, even if the crash happened after a promotion.

### Test-time selection (`engine/selector.py`)

This is where the teams cooperate. With no reference available:

1. Drop drafts that don't compile or don't match the interface.
2. Get a stimulus: the Breaker's multi-draft attack (`breaker` mode) or 120 random cycles (`random` mode, used as a control).
3. Simulate all drafts on it and group identical behavior.
4. The largest group wins. If the top groups are tied in size, the **Judge** model reads the spec and each tied group's outputs up to the first disagreement, and picks one.

Each record says how the pick was made: `single`, `majority`, `judge` or `fallback`.

### The final exam (`engine/final_eval.py`)

Runs on the 92 held-out problems, graded only by official testbenches.

| Metric | Meaning | Cost |
|---|---|---|
| `v0` | Builder v0, temperature 0 | Required |
| `vbest` | Latest Builder version, temperature 0 | Required |
| `vbest_selection` | Latest version, N drafts at 0.7, the latest Breaker picks one | Required (3–5 drafts) |
| `random_pick` | Expected pass rate of picking a draft at random | Free (same drafts) |
| `ceiling` | Passes if any draft passes: the best any selector could do | Free |
| `random_input_sel` | The same selection with random inputs instead of the Breaker | Free |
| `breaker_v0_sel` | The same selection with Breaker v0, to isolate what the Breaker learned | Optional |
| `ultra` | The big model (Nemotron 3 Super 120B) with the v0 playbook | Optional |
| `transfer_v0` / `transfer_vbest` | Gemma with the v0 vs the learned playbook: does what was learned transfer? | Optional |
| `ablation_nano_coach` / `ablation_main_coach` | Validation gain with the worker model as coach vs the main coach | From `ablation` |

- `v0`, `ultra` and `transfer_v0` don't depend on the loop, so `run` starts them right away, alongside self-play, in their own lower-concurrency lane.
- The headline bars (v0, latest, latest + Breaker) are computed on one common set of problems with no API errors. Excluded problems are counted in the notes.
- Every pass rate has a 95% bootstrap confidence interval.
- It also prepares UI material: **demo cases** (held-out problems where v0 fails and the latest version passes, with a waveform trace, preferring traces where the Breaker exposed the bug) and **selection examples**.
- Everything is cached under `runs/final/`. `assemble()` rebuilds `final.json` from whatever has finished, so it works after a hard stop.

### The LLM layer (`engine/llm.py`)

- **One door:** `LLMClient.chat()` is the only way any component calls a model. Real mode uses `AsyncOpenAI` pointed at `https://api.inference.crusoecloud.com/v1`; mock mode uses `MockProvider`.
- **Concurrency:** a semaphore (`SHADOWBOX_CONCURRENCY`, default 8) plus a client-side cap of 500 requests per minute per model (Crusoe's limit is 600 per model with a payment method on file).
- **Cost ledger:** every call appends a row to `runs/ledger.jsonl` (role, model, tag, tokens, cost, latency, finish reason). The spend cap is checked against the ledger total before every call, so it survives restarts.
- **Nemotron reasoning control:** sends `chat_template_kwargs` with `enable_thinking`, `low_effort` and `force_nonempty_content`. Worker reasoning defaults to off, the coach's and the Breaker's to low. A Builder playbook's `think` param overrides the worker default. `<think>` blocks are stripped from replies.
- **Determinism:** temperature-0 work sends a fixed seed. Sampled drafts don't.
- **Retries:** rate limits, timeouts, connection errors and 5xx responses are retried up to 6 times with exponential backoff and jitter. Coach and planner replies cut off at the token limit are retried once with double the budget. If a provider rejects `seed` or `chat_template_kwargs`, that parameter is dropped for that model.
- **Fatal errors** (bad key, unknown model, permission denied, other 4xx) raise `FatalLLMError` and stop the run with a clear message. Fix it and rerun the same command to resume.
- **Heartbeat:** while calls are flowing, `state.json` gets a fresh `updated_at` and spend at least every 30 s, so the UI can tell a live run from a dead one.
- **Output parsing:** `extract_code` takes the last fenced block that declares `TopModule` (with fallbacks). `extract_json` takes the last ```json block, then other blocks, then the outermost `{...}`.

### Time budget (`engine/budget.py`)

- `--minutes` sets a deadline. Throughput is measured from the ledger as finished work per second over the last 5 minutes of activity (a build counts as 1, an attack as 0.6; gaps over 2 minutes are treated as idle).
- Before each round, the loop estimates that round's duration (the average of the last two) plus the required final-exam work, adds a 15% safety margin, and stops if they don't fit.
- The final exam adds drafts 4 and 5 and the optional comparisons only while they fit.
- At deadline + grace, `asyncio.timeout` cancels everything and partial results are assembled.

### Storage, events and state (`engine/store.py`)

- **Atomic writes:** every JSON file is written to a temp file and renamed, so readers never see half a file.
- **`events.jsonl`:** an append-only log of human-readable events (`round_done`, `gate_result`, `llm_retry`, `time_budget`, ...). It's the UI's live feed, and each event is also printed to the console.
- **`state.json`:** the live status (status, phase, round, step, message, spend, versions, deadline, human interventions).
- **Which run readers see:** `select_run_dirs()` picks `runs/` if it has a state file, otherwise `runs_mock/`. `SHADOWBOX_DATA`, `SHADOWBOX_RUNS_DIR` and `SHADOWBOX_VERSIONS_DIR` override it.

### The API server (`server/api.py`)

A read-only FastAPI app. It never writes anything, and every response follows [docs/CONTRACT.md](docs/CONTRACT.md).

| Endpoint | Source |
|---|---|
| `GET /api/state` | `runs/state.json` |
| `GET /api/series` | `runs/series.json` |
| `GET /api/lineage` | `versions/lineage.json` |
| `GET /api/rounds` | scans `runs/round_<n>/` |
| `GET /api/rounds/{n}/match` | `runs/round_<n>/match.json` |
| `GET /api/playbooks/{team}` | scans `versions/<team>/v<n>/` |
| `GET /api/playbooks/{team}/{version}` | the playbook, its tool sources, tool stats |
| `GET /api/final` | `runs/final/final.json` |
| `GET /api/selection-examples` | `runs/final/selection_examples.json` |
| `GET /api/demo-cases` | `runs/final/demo_cases.json` |
| `GET /api/demo-config` | `demo.json` |
| `GET /api/events?since=<n>` | `runs/events.jsonl`, from line n |
| `GET /*` | the built UI in `web/dist/` |

- Missing, partial or corrupt files become empty-but-valid shapes (never a 404), so the UI can always render "waiting for the first round".
- `/api/*` responses carry `Cache-Control: no-store`.
- Tool names come from LLM output, so they're validated before they become file paths, and every served path is checked to stay inside its folder.
- Host and port: `SHADOWBOX_HOST` and `SHADOWBOX_PORT` (default `127.0.0.1:8000`).

### The web UI (`web/`)

- **Data flow:** `src/api.ts` has a typed fetcher per endpoint. Every response goes through `src/lib/normalize.ts`, so views can rely on the types in `src/types.ts`. `src/lib/DataContext.tsx` polls every 3 s while a run is going and every 10 s otherwise, and fetches only new events.
- **Views:**
  - **Overview:** live run panel, headline stats, the arms-race chart (Builder validation pass rate vs Breaker catch rate by round), the latest match grid, and the event feed.
  - **Live Match:** the latest round problem by problem, with code and waveforms, plus a walkthrough of test-time selection.
  - **Evolution:** every proposed change (accepted and rejected, with reasoning), playbook versions, and the toolbox with each tool's source and stats.
  - **Final Exam:** the held-out bars with confidence intervals and every comparison.
  - **Demo mode** (`src/views/demo/`): the 60-second scripted presentation.
- **Honesty badges:** MOCK DATA, FIXTURE DATA, API OFFLINE. The sample fixtures in `src/fixtures/` load only with `?fixtures=1`.

### Integrity rules (enforced in code)

- Agents never see reference designs or the held-out split. Only the harness reads `_ref.sv` and `_test.sv` files.
- The Builder never sees official test results while working on a problem.
- A Breaker "bug" counts only when the reference confirms it.
- Breaker skill is measured on a frozen pool, not a moving target.
- Builder changes are gated on validation, not on the training problems the coach studied, and the final judge is the held-out split.
- Mock and real runs never share folders, so fake numbers can't reach the demo.
- Coach-written tools run sandboxed and can't read the project folder.

### Failure handling

| Failure | What happens |
|---|---|
| Bad API key; unknown worker, coach or judge model; other 4xx | The run stops with a clear message. Fix it and rerun to resume |
| Wrong Ultra or Gemma model ID | That comparison is skipped with a warning event |
| Rate limits, timeouts, 5xx | Retried with backoff. If still failing, the item is marked errored, excluded from every score and gate, and retried on the next run |
| Reply cut off at the token limit | Coach or planner: retried once with double the budget. Builder: the debugger is told it was cut off. Breaker: a repair turn |
| Malformed coach JSON | One repair turn. If it still fails, that coach makes no proposals this round |
| Spend cap reached | Clean stop with everything saved. Raise `SHADOWBOX_SPEND_CAP` and rerun |
| Ctrl-C, `kill`, closed terminal | State saved. Rerun the same command to resume |
| Time budget | No new round if it won't fit; hard stop at deadline + grace with partial results |

---

## Configuration reference

Set these in `.env` or the shell. All of them live in `engine/config.py`.

| Variable | Default | Meaning |
|---|---|---|
| `CRUSOE_API_KEY` | (none) | Crusoe key. Without it, mock mode |
| `CRUSOE_BASE_URL` | `https://api.inference.crusoecloud.com/v1` | API endpoint |
| `SHADOWBOX_MOCK` | (unset) | `1` forces mock mode |
| `SHADOWBOX_WORKER_MODEL` | `nvidia/Nemotron-3.5-Lightning-30B-A3B` | Builder and Breaker model |
| `SHADOWBOX_COACH_MODEL` | `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B` | Coach model |
| `SHADOWBOX_JUDGE_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Tie-break judge |
| `SHADOWBOX_ULTRA_MODEL` | `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B` | Big-model comparison |
| `SHADOWBOX_TRANSFER_MODEL` | `google/gemma-4-31b-it` | Transfer comparison |
| `SHADOWBOX_SPEND_CAP` | `45` | Hard spend cap in USD |
| `SHADOWBOX_CONCURRENCY` | `8` | Parallel model calls. Scales nearly linearly if rate limits allow |
| `SHADOWBOX_BASELINE_CONCURRENCY` | `6` | Separate lane for the baselines that run alongside self-play |
| `SHADOWBOX_RPM` | `500` | Client-side requests per minute, per model |
| `SHADOWBOX_K` | `1` | Proposals per coach per round |
| `SHADOWBOX_DRAFTS` | `5` | Test-time drafts per held-out problem (minimum 3) |
| `SHADOWBOX_WORKER_THINKING` | `off` | Worker reasoning: `off`, `low` or `on`. Set `on` if quality is poor |
| `SHADOWBOX_COACH_THINKING` | `low` | Coach reasoning |
| `SHADOWBOX_BREAKER_THINKING` | `low` | Breaker reasoning |
| `SHADOWBOX_WORK_TEMP` | `0.0` | Temperature for normal work (drafts always use 0.7) |
| `SHADOWBOX_FINAL_ULTRA`, `SHADOWBOX_FINAL_TRANSFER`, `SHADOWBOX_FINAL_BREAKER_V0` | `1` | `0` skips that optional comparison |
| `SHADOWBOX_DATA` | `auto` | Which run the server and `status` show: `real` or `mock` |
| `SHADOWBOX_RUNS_DIR`, `SHADOWBOX_VERSIONS_DIR` | `runs/`, `versions/` | Override the output folders |
| `SHADOWBOX_HOST`, `SHADOWBOX_PORT` | `127.0.0.1`, `8000` | API server address |

Fixed constants in `engine/config.py`: gate margin 3, clean win 2, toolbox cap 6, tool evidence minimum 3, bug pool maximum 50, stimulus maximum 200 cycles, split seed 1234, and model prices per million tokens.

---

## Output layout

```
runs/                         (runs_mock/ in mock mode)
  state.json  series.json  events.jsonl  ledger.jsonl
  baseline/val_v0.json        Builder v0 on validation
  bug_pool.json               frozen bug pool
  hard_suite.json             saved bug-exposing stimuli per problem
  cache/                      result caches keyed on playbook fingerprint + settings
  round_<n>/                  match.json, *_proposals.json, *_gate.json, done.json
  final/                      final.json, test_*.json, drafts_d<i>.json, selection_*.json,
                              demo_cases.json, selection_examples.json
  ablation_nano_coach/        only after `ablation`
versions/                     (versions_mock/ in mock mode)
  lineage.json                every proposed change, with reasoning
  builder/  breaker/          current.json, v<n>/playbook.json, v<n>/tools/*.py,
                              candidates/<id>/, tool_stats.json
```

Real results in `runs/` and `versions/` are meant to be committed as evidence. Mock output, `.env`, `.venv/`, `.tools/`, `web/node_modules/` and `data/raw/` are git-ignored. Full shapes are in [docs/CONTRACT.md](docs/CONTRACT.md).

---

## Results from earlier runs

Earlier real runs were archived by renaming their folders (`runs_run1/` with `versions_run1/`, and so on; the `runs_pre*/` folders are aborted warm-ups). The current run always lives in `runs/` and `versions/`. Run 3 (30-minute budget, 7 rounds, about $0.96 in total) is the most complete so far. Its held-out results on 92 problems:

| | Pass rate |
|---|---|
| Builder v0 | 42.4% |
| Latest Builder (v1) | 44.6% |
| Random draft (expected) | 44.8% |
| Latest + Breaker selection (5 drafts) | 53.3% |
| Random-input selection | 54.3% |
| Best possible pick (ceiling) | 64.1% |
| Nemotron 3 Super 120B, v0 playbook | 68.5% |
| Gemma 4 31B, v0 playbook → learned playbook | 81.5% → 83.7% |

Of 42 proposals in run 3, the gate kept three: a Breaker rule to pulse reset (round 1), a Builder tool, `always_output_logic_check`, that flags outputs assigned in `always` blocks but not declared `reg` or `logic` (round 3), and a Breaker rule to pulse load signals (round 7).

These are single runs with wide confidence intervals. See `runs_run3/final/final.json` for the intervals and notes.

---

## Repository layout

```
engine/
  config.py        every tunable, model IDs and prices, .env loading
  llm.py           the one LLM client: Crusoe or mock, ledger, spend cap, retries, parsing
  mock_llm.py      offline fake model for free end-to-end testing
  dataset.py       VerilogEval loading, port parsing, exclusions, locked splits
  harness.py       Icarus compile, official grading, stimulus sims, ref and draft comparisons
  prompts.py       v0 prompts, coach and judge system prompts
  playbook.py      playbooks, versions, fingerprints, lineage, tool stats
  builder.py       Builder team: planner, writer, debugger, team drafting
  breaker.py       Breaker team: single and multi-draft attacks
  coach.py         evidence reports, proposals, validation, applying changes
  tools_runner.py  static screen and sandboxed execution of coach tools
  gatekeeper.py    cached evaluations, paired flips, accept rule
  bug_pool.py      the frozen bug pool
  selector.py      test-time selection: group by behavior, judge ties
  loop.py          setup, match, gates, series, settings sweep, resumable main loop
  budget.py        time budget and throughput estimates
  final_eval.py    held-out exam, comparisons, bootstrap CIs, demo material
  store.py         atomic JSON, events, state, run folder selection
  cli.py           command line entry point
server/api.py      read-only FastAPI over the engine's files; serves web/dist
web/               React + Vite + Tailwind UI (src/views, src/components, src/lib)
tests/             offline pytest suite
data/splits.json   locked splits (data/raw/ holds the downloaded dataset)
docs/CONTRACT.md   engine / API / UI data contract
demo.json          presenter settings for demo mode
PRD.md, DEMO_SCRIPT.md
```
