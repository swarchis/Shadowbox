# PRD: Shadowbox

Self-play agent teams that teach each other chip design. Like a boxer training against their own shadow, the system gets better by fighting itself.
Built for the Recursive Agents Hackathon (Cerebral Valley x Crusoe), Version N+1 track.

---

## 0. Instructions for any AI coding agent working on this repo

- **Never run `git commit`, `git push`, or any command that creates commits, tags, or branches on the user's behalf.** Stage nothing unless asked. The user commits manually. If you think a commit is a good idea, say so and stop.
- The product's own version history (Builder/Breaker versions) is stored as plain folders and a JSON log (see Section 8), **not** as git commits.
- Keep code simple: plain Python, no agent frameworks (no LangChain, CrewAI, etc.).
- All LLM calls go through Crusoe Managed Inference via the OpenAI-compatible endpoint. Never hardcode API keys; read from `CRUSOE_API_KEY` in env.
- Every LLM call must go through one wrapper that logs tokens and cost, retries with backoff on API errors, and enforces the hard spend cap (Section 12).
- The loop must be resumable: every step writes its result to disk before the next starts, and a restart picks up from the last completed step (Section 8).
- Test any new loop on 5 problems before running full rounds.
- Never let Builder or Breaker see reference solutions. Only the harness touches them.
- Never let any agent see the held-out test split.

---

## 1. Hackathon context

**Event:** The Recursive Agents Hackathon, hosted by Cerebral Valley and Crusoe, during the PyTorch Conference.
**Where:** Shack15, 1 Ferry Building Suite 201, San Francisco, CA 94111
**Format:** In person only. Bring government photo ID.
**Theme:** "Build a team of agents you can walk away from." Agents that take a goal, plan, spawn sub-agents, delegate, communicate, check their own progress, recover when things break, and keep going.

### Rules
- Repo must be public.
- Max 4 people per team. Solo allowed.
- Demo must only show what the team built during the hackathon. Judges must be able to clearly identify what was created at the event, or the team is disqualified.
- New work only: previous work or documents may be used **as references only. Direct code usage is not allowed.** (Coding agents: do not copy code from any prior project, including the user's rtl-env, into this repo. Ideas and designs from it may inform the build; all code is written fresh.)
- No code, data, or assets you don't have rights to.

### Banned project types
AI mental health advisor, basic RAG apps, Streamlit apps, image analyzers, "AI for education" chatbots, AI job application screeners, AI nutrition coaches, personality analyzers, anything giving medical advice, **any project where a dashboard is the main feature**, sports analyzers/coaches.

> Implication: our frontend is a visualization of the system, not the product. The product is the self-play engine.

### Tracks (all must be built on Crusoe Managed Inference)
1. **Done Means Done:** agents write their own definition of done, verify with tests or independent verifier agents, catch drift/loops, decide continue/re-plan/stop/ping human.
2. **Shared Brain:** shared memory layer every agent reads before working and updates after; current, lean, conflict-free, with measurable quality gains.
3. **Version N+1 (our track):** "Build an agent team on Crusoe Managed Inference that improves itself over time: after each run it reviews what worked and what didn't, then rewrites its own prompts, playbooks, tools, or team structure, and keeps a change only if it measurably helps. How can a team turn its own history into a better version of itself, and prove it with a before-and-after score on tasks it hasn't seen?"

### Judging
**Round 1** (~3 min live demo + 1 to 2 min Q&A, in judging rooms):
- Technicality: 40%
- Creativity and originality: 25%
- Live demo: 20%
- Future potential and AI impact: 15%

**Round 2** (top 6, on stage): same criteria, equal weighting.

### Prizes
- 1st: $14,000 + $1,000 You.com credits
- 2nd: $8,000 + $500 You.com credits
- 3rd: $3,000 + $250 You.com credits
- Best Use of NemoClaw & OpenShell: $100 Brev credits per person
- Best Use of Nemotron: NVIDIA RTX 5090

### Submission
Submission form with a **1 minute demo video** showing only what was built at the event. Repo public, demo link accessible, all teammates added.

### Sponsors and resources
- **Crusoe Managed Inference:** OpenAI-compatible API at `https://api.inference.crusoecloud.com/v1`. $50 credits via the hackathon form. One teammate creates the org and invites others so each gets their own key. **Confirm on day one whether credits are per person or per team.**
  - Relevant models: `nvidia/Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3-Super-120B-A12B`, `nvidia/Nemotron-3-Ultra-550B`, `nvidia/nemotron-3.5-lightning-30b-a3b`, `google/gemma-4-31b-it`, `openai/gpt-oss-120b`, DeepSeek and GLM models.
  - Known pricing (per 1M tokens, verify in console): Nemotron 3 Ultra $1.00 in / $3.20 out; Nemotron 3 Nano Omni Reasoning $0.30 in / ~$2 out; gpt-oss-120b $0.05 / $0.20; Gemma 4 31B $0.14 / $0.40.
  - Starter repo: `crusoecloud/crusoe-developer-hub` → `examples/hackathons/crusoe-cv-recursive-agents-hackathon`
- **NVIDIA Nemotron:** open models built for agent loops, hybrid Mamba-Transformer MoE, long context.
- **NVIDIA NemoClaw / OpenShell:** sandbox for always-on agents with guardrails on network, filesystem, process, inference. Optional: use it to sandbox agent-written tools only if one person owns it end to end.
- **You.com:** search API. Not needed for this project.
- Discord: channels #crusoe, #nvidia, #questions for sponsor help.

---

## 2. One-liner and pitch

**One-liner:** Two AI teams play against each other at chip design. One builds circuits, one tries to break them. Every bug found makes the builder smarter, which forces the breaker to get craftier. On new problems, the breaker keeps working for the builder: it attacks several drafts at once and picks the one that survives. The models never change; the teams rewrite themselves.

**Pitch framing (lead with mechanism, domain is proof):**
- Real chip companies split into design engineers and verification engineers whose job is to break the design. We automated that rivalry.
- Self-play means the difficulty rises on its own, so improvement doesn't plateau the way a fixed benchmark loop does.
- The Breaker isn't just a sparring partner. On unseen problems, with no answer key, it finds inputs where the Builder's drafts disagree, and that decides which draft ships.
- What each team learns is a portable folder of rules and tools, not weights. Hand it to a different model and that model gets better too.

**Stage lines:**
- "The model stays frozen. The team around it rewrites itself."
- "Same model, version 1 solves X%, version N solves Y%, on problems it has never seen."
- "Verification is the bottleneck in chip design. We built a team that gets better at it by fighting itself."

---

## 3. How it meets the Version N+1 requirements

| Track requirement | How we meet it |
|---|---|
| Agent team on Crusoe Managed Inference | Builder team, Breaker team, two coaches, all on Crusoe (Nemotron) |
| Reviews what worked and what didn't after each run | Coaches read every failure trace and every rejected/accepted change |
| Rewrites prompts, playbooks, tools, or team structure | Coaches edit prompts, playbook rules, and agent-written tools (team roster is fixed for the hackathon) |
| Keeps a change only if it measurably helps | Gatekeeper runs candidate and current on the same validation problems; keep only if it wins by a fixed margin |
| Before/after score on unseen tasks | Locked held-out test split; v0 vs vBest scored with official testbenches only, 3 runs with error bars |

**Judging criteria mapping:**
- Technicality: multi-agent self-play, automatic bug validation via reference oracle, reference-free test-time selection via differential testing, agent-written sandboxed tools, gated version lineage with paired statistics, resumable loop.
- Creativity: self-play / adversarial co-evolution is rare at hackathons; hardware domain is rare; the adversary becoming a test-time verifier is novel.
- Live demo: arms race chart, live match (red → green), evolution receipts, transfer swap.
- Future potential: automated verification for chip design; the loop works for any domain with an automatic grader.

---

## 4. Core concepts (plain English)

- **Model vs agent:** the model is the brain (e.g. Nemotron Nano). An agent is that brain with a job: instructions, tools, and a loop. One model powers several agents.
- **We are not post-training.** No weights change. What changes is each team's playbook: instructions, rules, and toolbox.
- **Builder team:** reads a circuit spec, writes Verilog, fixes it when tests fail.
- **Breaker team:** reads the spec and the Builder's code, writes targeted test inputs to make it fail.
- **Reference oracle (training only):** VerilogEval ships a correct reference design for every problem. During training, the harness runs the Breaker's test inputs on both the reference and the Builder's design. If outputs differ, it's a real bug. No fake bugs possible. Agents never see the reference.
- **Test-time selection (no reference needed):** on unseen problems, the Builder writes 3 to 5 drafts, sampled at temperature ~0.7 on purpose so they actually differ. The Breaker writes inputs designed to make them disagree. The harness runs every draft on those inputs and groups drafts by behavior. The largest group wins; if there's a tie, a Judge agent reads the spec and the disputed input and picks. This is how the Breaker's skill reaches the held-out score directly.
- **Coaches:** one per team. Read the round's results, find patterns, propose changes to their team's playbook.
- **Gatekeeper:** tests each proposed change against the current version on the same problems. Keep only if it wins by a clear margin.
- **Frozen bug pool:** a fixed set of buggy Builder designs collected early. The Breaker is always scored against this pool, so its score measures skill and doesn't drop just because the Builder improved.
- **Toolbox:** coaches can write small Python tools (e.g. a checker) when the same mistake shows up across many problems. Tools survive only if they help.

### What tools might look like
We do not decide the tools in advance; they come from whatever failure patterns the coach actually sees. Likely candidates: a lint wrapper (`verilator --lint-only`, `iverilog -Wall`), a "write a quick testbench and simulate" tool, port/width/reset checkers, and guards against SystemVerilog constructs iverilog doesn't support. Early accepted changes will probably be mundane rules (e.g. "always name the module TopModule"). Those are fine receipts.

---

## 5. Data

- **Benchmark:** VerilogEval v2, spec-to-RTL task (NVIDIA, MIT license). 156 problems, each with spec, reference solution, and testbench. Simulated with Icarus Verilog using the same flags and pass rule as VerilogEval's own scripts. **We do not write custom problems** (decided: credibility and time; a contamination-free bonus set was considered and dropped).
- **4 problems excluded** because even their reference fails the official grading (3 testbenches hit their own TIMEOUT, 1 testbench has mismatched ports). 152 problems remain.
- **Known benchmark weakness (Q&A ammo):** some official testbenches are weak. E.g. `Prob053_m2014_q4d`: the input starts as X, so the reference output is X for the whole test and every design passes. Our harness starts inputs at 0 and catches bugs there.
- **Three locked splits**, chosen once at start with a fixed seed and saved to `data/splits.json`:
  - **Train (30):** teams play on these; coaches see all traces.
  - **Validation (30):** gatekeeper uses these to accept/reject changes. Coaches see only aggregate scores, never traces. The frozen bug pool is built from these problems.
  - **Held-out test (92):** used only for the final evaluation. No agent ever sees these. Larger than train/val on purpose: it is run once, and a bigger test set gives tighter error bars (~±10 points).
- Splits are stratified by combinational vs sequential. Don't go below ~20/20 for train/val: the coach would see too few failures and the gate would accept noise.
- **Contamination note:** VerilogEval is public and may be in model training data. This affects v0 and vBest equally, so the relative improvement is still valid.
- **Honest caveat:** after many rounds of gating, validation is partly "used up" (accepted changes may include lucky wins). That's why the headline number is held-out only, never validation.

---

## 6. System architecture

### Agents
| Agent | Model | Job |
|---|---|---|
| Builder: Planner | Nemotron 3 Nano | Optional (off in v0; a coach can turn it on): reads spec, outlines design |
| Builder: Writer | Nemotron 3 Nano | Writes Verilog |
| Builder: Debugger | Nemotron 3 Nano | Fixes compile errors and its own tools' findings, max N attempts. Never sees official test results (they encode the reference and don't exist on held-out problems) |
| Breaker: Attacker | Nemotron 3 Nano | Reads spec + Builder code, writes targeted stimulus |
| Judge | Nemotron 3 Nano | Test time only: breaks ties between groups of disagreeing drafts using the spec |
| Builder Coach | Nemotron 3 Super or Ultra | Reviews Builder failures, proposes changes |
| Breaker Coach | Nemotron 3 Super or Ultra | Reviews which attacks found real bugs vs missed, proposes changes |

The roster is fixed for the hackathon. Coaches change prompts, rules, and tools only.

### Harness interface parsing
The harness reads each problem's reference module header to get port names, widths, direction, clock, and reset. That's needed to turn Breaker JSON into a testbench and to compare outputs. Budget real time for this in milestone 1; sequential problems (clocks, resets, multi-cycle behavior) are where it breaks.

### Breaker test format
Breaker outputs a stimulus sequence (input values per clock cycle) as JSON. The harness turns it into a testbench that drives two or more designs and compares outputs cycle by cycle.
- **Training:** drives the reference and the Builder design. Mismatch = valid bug.
- **Test time:** drives all Builder drafts. Mismatch = disagreement, used for selection.

### Scoring
- **Builder score (official):** pass rate using VerilogEval's official testbenches.
- **Builder score (hard):** pass rate against official tests + accumulated valid Breaker tests (harder suite that grows over time).
- **Breaker score (skill):** fraction of designs in the frozen bug pool where it finds a valid bug. Tracked separately: "subtle catches," bugs the official testbench missed.
- **Held-out final:** official testbenches only, so the number is comparable to the public benchmark.

### Frozen bug pool
Built once after Builder v0 runs on validation: every v0 design that fails official tests, plus extra v0 drafts sampled at higher temperature (~0.7) to enlarge it. Target 30 to 50 buggy designs. Saved to `data/bug_pool/` and never changed. Also tag which bugs the official testbench misses but the Breaker's tests catch, since those are the Breaker's real value-add.

**Early check (do in the first hours):** of the Breaker's valid bugs on train, what share did the official testbench miss? If it's near zero, lean on test-time selection as the Breaker's main role in the pitch.

---

## 7. The loop

```
init Builder v0, Breaker v0 (hand-written baseline playbooks)
run Builder v0 on validation → build frozen bug pool
time one full round; set R and candidates-per-round from that

for round in 1..R:            # each step checkpointed to disk; restart resumes here
    # 1. Match
    Builder designs all train problems
    Breaker attacks each design
    harness validates attacks against reference → list of real bugs
    log everything to runs/round_<n>/

    # 2. Builder improves
    Builder Coach reads train failures (official + Breaker bugs)
    proposes K changes (K=1 by default; raise if round timing allows):
        prompt edit | playbook rule | new tool
    Gatekeeper runs each candidate and the current Builder on the SAME validation problems
    accept the best candidate only if it wins by >= 3 net problems flipped
        (problems it newly passes minus problems it newly fails), else reject all

    # 3. Breaker improves
    Breaker Coach reads which attacks found bugs, which missed
    proposes K changes
    Gatekeeper scores each candidate and the current Breaker on the frozen bug pool
    accept the best only if it catches >= 3 net more pool designs, else reject

    save versions/builder/vN, versions/breaker/vN, append lineage.json

final (held-out, official testbenches only):
    # required, never cut
    Builder v0       × 1 run at temp 0 → pass rate, 95% bootstrap CI over problems
    Builder vBest    × 1 run at temp 0 → pass rate, 95% bootstrap CI over problems
    (v0, Ultra and Gemma-v0 don't depend on the loop, so they run in parallel with it)
    vBest drafts: 3 to 5 per problem at temp ~0.7 (generated once, reused below)
    vBest + test-time selection with Breaker vBest

    # free, from the same drafts (no LLM calls)
    random pick:  mean pass rate of a single draft (isolates the selection effect
                  from the temp 0 vs 0.7 difference)
    ceiling:      share of problems where ANY draft passes (best selection could do)
    random-input selection: same drafts, random stimulus instead of the Breaker
                  (answers "random fuzzing would do the same")

    # optional, cut per Section 13
    selection with Breaker v0 vs Breaker vBest (only adds Breaker calls)
    plain Nemotron Ultra, v0 playbook × 1 run (comparison)
    transfer: Gemma 4 with v0 playbook vs Gemma 4 with vBest playbook + tools
    ablation: repeat 3 rounds with a Nano coach on small splits; compare gain vs Super/Ultra coach
```

Selection is reported as "captures X of the Y-point gap between random pick and ceiling."

### Noise controls
- Regular Builder and Breaker runs and all gating use temperature 0 (or the lowest setting the model handles without looping; reasoning models can loop at 0), with a fixed seed if Crusoe supports it. The only exception is test-time drafts, which use ~0.7 on purpose.
- Gating is always paired: same problems, same settings, candidate vs current.
- Margin of ≥3 net problems flipped. A plain "higher score" is not enough.
- Final held-out numbers use one temperature-0 run each, with 95% bootstrap confidence intervals over problems. (Three runs at temperature 0 come out near-identical, so the real uncertainty is which problems are in the test split; this saves ~220 builds.)
- **Time budget:** `run --minutes 60` keeps starting rounds only while there is time for another round plus the final exam (estimated from measured round times). Target: the whole system in about an hour.

---

## 8. Playbook, versions, and toolbox

### Playbook (one per team, one per version)
`versions/builder/v3/playbook.json`
```json
{
  "version": 3,
  "parent": 2,
  "prompts": { "planner": "...", "writer": "...", "debugger": "..." },
  "rules": ["Run lint_check before submitting", "..."],
  "tools": ["lint_check", "port_check"],
  "max_debug_attempts": 3
}
```
Tools live at `versions/builder/v3/tools/<name>.py`.

### Lineage log
`versions/lineage.json`: one entry per proposed change, accepted or rejected:
round, team, change type, coach's reasoning in plain English, validation score before/after, net problems flipped, accepted (bool), cost. This powers the evolution view and the "receipts."

### Checkpointing and recovery
- Each step (match, coach proposal, each gate run) writes its result to `runs/round_<n>/` before the next step starts.
- On restart, `loop.py` reads `lineage.json` and the run folders and resumes at the first incomplete step. No work is redone.
- The LLM wrapper retries failed calls with exponential backoff; a problem that keeps failing is marked errored and skipped, not fatal.
- The spend cap stops the loop cleanly at a checkpoint.

### Tool guards (prevent narrow, useless tools)
1. Coach may only create a tool if the same failure pattern appears in **3+ different problems**.
2. Tool must take any spec + any Verilog as input; never hardcode a problem.
3. Validation uses different problems than the ones that inspired the tool. Narrow tools fail to move the score and get rejected automatically.
4. Usage tracking: every tool logs times run and times it caught something. Tools that never fire get pruned.
5. Toolbox cap of 6 per team. A new tool must beat the weakest existing tool to get in.

### Tool execution safety
Agent-written code runs sandboxed. Default: subprocess in a temp dir with timeout, no network, read-only inputs. Optional: NemoClaw / OpenShell (also targets that prize) if one person owns it.

---

## 9. Tech stack

**Backend (Python 3.11+)**
- `openai` SDK pointed at Crusoe base URL
- `asyncio` for parallel problem runs (rate limit with a semaphore)
- **Icarus Verilog (`iverilog`, `vvp`)** via subprocess: compile + simulate, outputs pass/fail and VCD waveforms
- **FastAPI** server exposing run state and history over REST, read from the log files. The frontend polls; no live streaming.
- Storage: plain files. `runs/` (JSONL event logs), `versions/` (playbooks + tools), `data/splits.json`, `data/bug_pool/`. No database.

**Frontend (visualization layer, not the product)**
- **React + Vite + Tailwind**
- **Recharts** for charts
- **WaveDrom** (or a simple custom SVG) to render signal waveforms from VCD
- Reads from FastAPI over REST (polling)

### Repo layout
```
/engine
  llm.py          # Crusoe client wrapper, cost tracking, retries, spend cap
  harness.py      # iverilog compile/sim, port parsing, reference + differential comparison, scoring
  builder.py      # builder team agents
  breaker.py      # breaker team agents
  selector.py     # test-time selection: drafts + breaker + judge
  coach.py        # both coaches
  gatekeeper.py   # paired accept/reject logic
  bug_pool.py     # builds the frozen bug pool
  tools_runner.py # sandboxed tool execution
  loop.py         # main self-play loop, checkpoint/resume
  final_eval.py   # held-out, test-time selection, Ultra baseline, transfer, ablation
/server
  api.py          # FastAPI (REST)
/web              # React app
/data             # VerilogEval problems, splits.json, bug_pool/
/versions         # playbooks, tools, lineage.json
/runs             # per-round logs
```

---

## 10. Frontend views (for demo and video)

1. **Arms Race chart (hero visual):** two lines over rounds. Builder validation pass rate, and Breaker catch rate on the frozen bug pool. Accepted changes marked as dots; rejected as hollow dots.
2. **Live Match:** split screen. Left: Builder's Verilog. Right: Breaker's attack. Bottom: waveform with the mismatched signal highlighted, big red/green verdict. Second mode: test-time selection, showing several drafts, the disputed input, and which draft won.
3. **Evolution:** one timeline of every proposed change, accepted and rejected, with the coach's plain-English reasoning and net problems flipped. Tool changes appear as cards in the same timeline: born in round N, times fired, problems fixed, click to see the code.
4. **Final Exam:** bar chart on held-out with error bars.
   - Main bars: Builder v0, Builder vBest, vBest + Breaker selection.
   - Selection detail: random pick, random-input selection, Breaker selection, and the ceiling as a dashed line.
   - If built: Breaker v0 vs vBest selection, plain Ultra, Gemma v0 playbook vs Gemma vBest playbook (transfer).

---

## 11. Demo plan

### 1-minute demo (primary)
The demo is one minute. Script and scene list: `DEMO_SCRIPT.md`. It is a single screen recording of the frontend's Demo mode (auto-plays 6 scenes on a 60-second timeline) with a webcam bubble for faces; no video editing. Scenes: intro with team names, the problem, arms race, Breaker at test time, final exam, closer. Everything else (evolution timeline, toolbox, live match, honesty panel, ablation) is Q&A material in the app's tabs.

### Extended live demo (3 min, only if the slot allows)
- **0:00 Hook:** "Two AI teams fighting over chip design. Models frozen. Version 1 solves X%, version N solves Y% on problems it has never seen."
- **0:20 Arms Race chart:** show both teams improving round by round.
- **0:45 Live match, old vs new:** pick a validation or held-out problem where v0 fails and vBest passes, based on what the lineage actually produced. Show v0 failing (red), then vBest using whatever rule or tool it learned to fix it (green). Do not script this around a specific tool in advance or nudge the system toward a planned story.
- **1:20 Breaker at test time:** on a held-out problem, show drafts disagreeing on a Breaker-found input and the surviving draft being picked. "No answer key. The breaker decides."
- **1:50 Evolution:** two or three changes with coach reasoning, one rejected change, tool receipts.
- **2:20 Final Exam chart:** held-out scores with error bars.
- **2:40 Transfer swap:** Gemma with the v0 playbook vs Gemma with the vBest playbook. End on the jump.

### Submission video
Same recording as the 1-minute demo.

### Must-haves
- Leave the self-play loop running in the background so there are many rounds to show.
- Pre-recorded backup of the live match in case wifi/API fails.

---

## 12. Budget and time

Estimated with worst-case pricing for splits of 30 / 30 / 92. **`python -m engine.cli smoke` measures real latency and cost on 5 problems and prints a projection; trust that over this table.**
- One Builder attempt (write + up to 2 fixes): ~2 to 3 calls ≈ 2.5¢ on Nano. Breaker attack: ~1 call ≈ 1¢.
- Setup (Builder v0 on val, 2 extra drafts for the bug pool, Breaker v0 on the pool): ≈ $3
- One round at K=1 (train match, Builder gate on 30 val, Breaker gate on the pool, two coach calls): ≈ $2
- 6 rounds ≈ $12
- Final exam: v0 + vBest on 92 held-out ≈ $5; 5 drafts × 92 at temp 0.7 ≈ $11.50 (3 drafts ≈ $7); Breaker + Judge for selection ≈ $2 (+$2 for the Breaker-v0 comparison); plain Ultra ≈ $4; Gemma v0 + vBest ≈ $1
- Nano-coach ablation (3 Builder-only rounds) ≈ $3

**Total ≈ $40 to $45.** The default hard cap is $45 (`SHADOWBOX_SPEND_CAP`). If credits are per team and tight: 3 drafts, fewer rounds, then the money cuts in Section 13.

**Time:** target about one hour end to end with `run --minutes 60`. The biggest lever is concurrency (`SHADOWBOX_CONCURRENCY`, default 8); the second is Nemotron's thinking mode (`SHADOWBOX_WORKER_THINKING=off` by default for workers).

Controls (built in):
- Hard spend cap enforced against the persisted cost ledger, so it survives restarts
- Per-call max output tokens
- Max debug attempts 2 (a coach may change it within 1 to 3)
- Retries with backoff; a problem whose calls keep failing is marked errored and skipped
- Everything checkpointed: rerunning a command resumes without re-billing finished work

---

## 13. Build plan (priority order)

Rule: always have a working demo. Each milestone must be demoable on its own.

1. **Harness:** load VerilogEval, parse ports/clock/reset from the reference header, compile/sim with iverilog, score with official testbench, compare designs on arbitrary stimulus. Verified on all 156 references and 366 mutants (agrees with the official grader except where the official test is weak).
2. **LLM wrapper:** Crusoe client, cost logging, retries with backoff, spend cap.
3. **Builder v0** solving train problems end to end. Baseline score. Pick the temperature setting here.
4. **Builder Coach + paired Gatekeeper** with prompt/rule changes only. One full improvement round working end to end, checkpointed and resumable. **Time this round.** *(This alone is a valid Version N+1 submission.)*
5. **Start the loop running** in the background.
6. **Breaker + frozen bug pool + Breaker Coach:** self-play on top. Run the early check (share of Breaker bugs the official TB missed).
7. **Test-time selection:** drafts + Breaker + Judge, tested on validation first.
8. **Toolbox:** coach-written tools, guards, sandbox.
9. **Frontend:** Arms Race chart and Live Match first, then Evolution, then Final Exam.
10. **Final eval:** held-out v0 vs vBest (3 runs), test-time selection with random-pick / ceiling / random-input comparisons, then optional items per the cut lists below.
11. **Record video and submit.**

### Cut order when behind
**Required no matter what:** held-out v0 vs vBest vs vBest + Breaker selection, plus the free comparisons from the same drafts (random pick, ceiling, random-input selection). Random-input selection is cheap to build and answers the most likely judge question, so it is protected.

Time and money are separate constraints, so there are two lists.

**Short on time** (cut the item that saves the most build effort first):
1. Nano-coach ablation
2. Breaker v0 vs vBest selection comparison
3. Toolbox (keep prompt and rule changes)
4. Breaker coach (keep the Breaker itself for selection; switch to the fallback pitch in Section 16)

Gemma transfer and the Ultra comparison are not on this list: they reuse the same code with a different model name, so cutting them saves almost no time.

**Short on money** (cut the item that saves the most credits first):
1. Nano-coach ablation
2. Test-time drafts from 5 down to 3
3. Ultra comparison
4. Gemma transfer
5. Fewer self-play rounds

Suggested split for 4 people: (A) harness + scoring + port parsing, (B) agents + coaches + gatekeeper + loop, (C) frontend + API, (D) breaker + bug pool + test-time selection + toolbox, then everyone on eval/video.

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Too few rounds to show improvement | Get milestone 4 working first; loop runs in background while the rest is built; time a round early |
| Improvement small or noisy | Paired gating with ≥3 net-flip margin; temperature 0; held-out reported as 3 runs with error bars |
| Validation overfit from repeated gating | Headline number is held-out only; margin rule limits lucky accepts |
| Breaker finds few bugs the official TB misses | Measured early; frozen pool keeps its score meaningful; test-time selection is its main contribution to held-out |
| Breaker score falls as Builder improves | Always scored against the frozen bug pool, not the current Builder |
| Baseline too high (no headroom) or too low | Nano for workers; sanity check baseline on a few problems first; pick harder problem subsets if needed |
| Coach writes useless/buggy tools | Tool guards + sandbox + gatekeeper; toolbox can be empty and the demo still works |
| Port/clock/reset parsing breaks on sequential problems | Budgeted in milestone 1; skip problems the parser can't handle, and log them |
| Transfer shows no gain | Gemma v0 baseline makes the comparison honest; if no jump, close on Final Exam instead |
| Judges don't know hardware | Explain in plain English, show red/green and waveforms, lead with mechanism |
| Loop crashes or API errors overnight | Checkpoint/resume, retries with backoff, errored problems skipped |
| Rate limits / wall-clock | Semaphore on concurrency; time one round; shrink splits or K |
| Credits run out | Spend cap, smaller splits, Nano everywhere except coaches |
| API/wifi failure during demo | Pre-recorded backup video; cached results for charts |

### Q&A prep
- **Is this RL?** No weights change. It's search over the team's playbook and tools, driven by self-play.
- **Isn't this just DSPy / prompt optimization?** Three differences: the opponent co-evolves so difficulty rises on its own; the adversary becomes a reference-free verifier at test time; and the teams write their own tools, not just prompts.
- **Isn't this just distillation from a bigger coach model?** We ran the ablation: with a Nano coach, the gain was [X]. Plain Ultra on its own scores [Y]. (Fill in from real results; don't claim until measured.)
- **Prior art?** AutoChip and VerilogCoder generate and fix designs; we co-evolve a builder and breaker with gated, portable playbooks.
- **Why not fine-tune?** Not feasible within the hackathon, and the learned playbook is inspectable and portable across models.
- **Contamination?** Same for v0 and vBest, so the gain is real.
- **How do you know bugs are real?** In training, every Breaker test is checked against the reference design automatically.
- **Wouldn't random fuzzing do the same?** We measured it: random-input selection on the same drafts scores [X], Breaker selection scores [Y]. (Fill in from real results. If random matches the Breaker, say so honestly and lean on the self-play results instead.)
- **How does selection work without a reference?** Drafts that behave the same on Breaker inputs are grouped; the largest group wins, and a Judge breaks ties using the spec.
- **Does it generalize?** Held-out problems the agents never saw, plus transfer to a different model with a matched baseline.

---

## 15. Future applications

Honesty rule for the pitch: everything here is framed as future scope. Only claim what is actually implemented in the repo. If something was started but not finished, show the partial work and say exactly how far it got.

### 15.1 Post-training on self-play output (main future pitch)

Today the teams store what they learn in playbooks and tools. The next step is moving that learning into the model's weights. Three ways the arena feeds post-training:

1. **Playbook distillation (context distillation).** Playbooks are plain instruction files (rules, prompts) plus tool scripts. Train the model to behave as if the playbook were in its prompt, so it no longer needs it. The playbook becomes the teacher; the weights become the student.
2. **Training on verified wins (supervised fine-tuning).** Every correct Builder design and every real Breaker bug has already been checked against the reference design. The arena produces clean, labeled training data for free, and more of it every round.
3. **The arena as an RL environment.** Pass/fail and bug-found are automatic rewards. Because the Breaker keeps getting craftier, the problems get harder on their own: a self-generating curriculum. This is the strongest version of the future story: a reinforcement learning environment for chip verification that never runs out of hard problems.

Pitch line: **"Today the teams store what they learn in playbooks. Next, that learning goes into the weights."**

Why we didn't do it now: fine-tuning isn't feasible within the hackathon on $50 of credits, and the track asks for self-improvement through prompts, playbooks, tools, and structure. Keeping learning in files also makes it inspectable and portable for the demo.

### 15.2 Chip quality, not just correctness (gate count)

Pass/fail only says the circuit works. Yosys can count how many logic gates a design needs. Fewer gates = smaller, cheaper, lower-power chip (same Lego model, fewer bricks). Optional second metric: logic depth (rough proxy for speed).

**Not built at the hackathon.** Pitch it strictly as future scope: "Next, gate count becomes a second optimization target alongside correctness." Only say "we started this" if something real exists in the repo.

### 15.3 Team structure changes

Letting coaches add, remove, or merge agents (e.g. add a Builder Reviewer) is the natural next step for the "team structure" part of the track. Cut from the hackathon build to keep scope manageable.

### 15.4 Beyond chip design

The loop works anywhere there's an automatic grader and a reference: SQL queries, compilers, smart contracts, numerical code. Chip design is the proof because it's one of the hardest domains to verify.

---

## 16. Pitch decisions (agreed)

- **Lead with the mechanism, use the domain as proof.** "We built agent teams that improve by fighting each other and inventing their own tools. We proved it on chip design, one of the hardest domains to verify." Do not pitch it as "Version N+1 but for Verilog."
- **Core line:** "The model stays frozen. The team around it rewrites itself."
- **Real-world anchor:** chip companies split into design and verification engineers. We automated that rivalry. Verification is the bottleneck in chip design.
- **Self-play is the creative hook.** Difficulty rises on its own, so improvement doesn't plateau like a fixed benchmark loop.
- **The Breaker earns its place at test time.** Show it picking the surviving draft on an unseen problem with no answer key.
- **Receipts, from what actually happened.** Show the changes and tools the lineage really produced, when each was born, and how many problems it fixed. Show at least one rejected change so the filter is visibly real. Don't script the story in advance.
- **Transfer is the closing moment,** always shown as Gemma v0 playbook vs Gemma vBest playbook. "Skills you can copy-paste between AIs." If there's no jump, or transfer was cut, close on the Final Exam instead.
- **Small vs big model is a bonus, not a promise.** If evolved Nano beats plain Ultra, lead with it. If not, use fallbacks: gap closed ("started 30 points behind, now 8 behind at a tenth of the cost"), cost per solved problem, or transfer. Don't claim it on stage until the number exists.
- **Have the distillation answer ready** from the Nano-coach ablation.
- **Frame selection against its ceiling:** "Selection captures X of the Y-point gap between a random draft and the best possible pick."
- **Fallback pitch if the Breaker coach is cut:** there's no co-evolution, so drop "the breaker gets craftier" and the two-line arms race. Pitch instead: "A builder team that rewrites itself, plus an adversarial verifier that picks the right draft on problems with no answer key." The Arms Race chart becomes a single Builder line, and Breaker v0 vs vBest selection is dropped.
- **Plain English for judges.** No Verilog literacy required: red/green verdicts, waveforms, coach reasoning in sentences.
- **Future scope:** post-training on self-play output (15.1), gate count (15.2), team structure changes (15.3), clearly labeled as future.
- **Frontend is a visualization, not the product,** to stay clear of the "dashboard as main feature" ban.

---

## 17. Out of scope (for the hackathon build)
- Fine-tuning or any weight updates (future scope, Section 15.1)
- Yosys / gate count (future scope, Section 15.2)
- Roster or team-structure changes (future scope, Section 15.3)
- Live event streaming to the frontend (polling the REST API is enough)
- Real FPGA or physical hardware
- Full PPA optimization / place-and-route
- You.com integration
- Any dashboard-first product framing
