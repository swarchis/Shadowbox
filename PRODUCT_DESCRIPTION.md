# Shadowbox

**AI teams that get better at chip design by fighting each other. The model never changes.**

Chip companies run two teams. One builds the design, the other tries to break it, and that back-and-forth (verification) is the slowest, most expensive part of making a chip. AI can write hardware code now, but it doesn't get any better on its own. Shadowbox puts that same fight inside an agent system and lets it run.

## What it does

Two agent teams on NVIDIA's Nemotron spar over Verilog. The Builder writes circuits from plain-English specs in NVIDIA's VerilogEval benchmark. The Breaker writes input sequences meant to make those circuits fail. A real simulator (Icarus Verilog) checks every result against a hidden reference design, so scoring is objective. No AI grades another AI.

After each round, a Coach on each side reads its team's losses and proposes a change to its own playbook: a prompt, a rule, a setting, or a brand-new Python checking tool it writes itself. A Gatekeeper tests every proposal on problems the Coach never saw and keeps it only if the score goes up. Most don't make it. That's the point.

Then, on real problems with no answer key, the two teams work together. The Builder writes five drafts, the Breaker hunts for the inputs where those drafts disagree, and the majority behavior ships. Engineers get code they can trust, plus the exact edge cases worth checking by hand.

## Technicality

This is a full self-improving system, not a prompt wrapped in a UI.

- **Four Nemotron-family roles on Crusoe.** Nemotron 3.5 Lightning is the worker for both teams, Nemotron 3 Super 120B runs both Coaches and serves as the big-model baseline, and Nemotron 3 Nano judges test-time selection. Gemma 4 31B is served alongside for a transfer test.
- **Agents write and run their own tools.** Coach-written Python checkers run inside a macOS `sandbox-exec` sandbox. One that survived the gate flags outputs assigned in `always` blocks but never declared `reg` or `logic`, a classic Verilog mistake.
- **Held-out discipline.** Locked train, validation and held-out splits are committed to the repo. The official grade is hidden from every agent, and the dashboard labels it that way.
- **Built to run unattended.** One client logs every call's tokens and cost, enforces a spend cap, retries rate limits with backoff, and caches responses so an interrupted run resumes without paying twice. A time-budgeted scheduler starts a new round only if that round and the final exam still fit before the deadline.
- **229 offline tests** cover simulation, gating math, the sandbox, the API contract, and the real Crusoe client path against a faked API.

## Live demo

The dashboard streams a run as it happens. You see each circuit's block diagram next to the Builder's Verilog, the Breaker's attack with the exact cycle where the output went wrong, and the official grade last. An Arms Race chart plots both teams climbing round by round, with filled dots for kept changes and hollow ones for rejects. The Evolution tab shows every proposal a Coach ever made, its reasoning, and the code of any tool it wrote.

Our recorded run: 7 rounds in about 26 minutes, zero human interventions, 3,466 LLM calls, $0.96 total.

## Results

All of these come from that one run, on the same frozen Nemotron model.

| | Before | After |
|---|---|---|
| Builder, validation pass rate | 43.3% | 50.0% |
| Breaker, bug-catch rate | 68.3% | 80.5% |
| 92 held-out problems, learned playbook | 42.4% | 44.6% |
| 92 held-out problems, + Breaker picking from 5 drafts | 42.4% | **53.3%** |
| Playbook moved to Gemma 4 31B | 81.5% | 83.7% |

The Gatekeeper kept 3 of 42 proposals: a Breaker rule to pulse reset, the Builder's lint tool, and a Breaker rule to pulse load signals. We'll be straight about the limits. The 42.4% to 44.6% gain is two problems, and the confidence intervals overlap. The real jump comes from Breaker-assisted selection, and random-input selection does about as well today. Making the Breaker's attacks beat random inputs is the next thing we're working on.

## Creativity and originality

Self-play has trained game-playing AIs for years. Shadowbox applies it to something with real stakes, and it changes what gets trained. There's no gradient and no fine-tuning. The thing that learns is the team around the model: its rules, its tools, its memory. And since the opponent adapts every round, the bar rises as the team gets better.

It also borrows the actual structure of a chip company (design versus verification) instead of inventing an abstract agent setup.

## Future potential and AI impact

Everything Shadowbox learns lives in plain text and plain Python. A person can read why the system got better, and the gate guarantees each kept change earned its place on data the Coach never saw. When a stronger model ships, you bring the playbook with you. The Gemma result is an early sign that works.

The pattern is bigger than Verilog. Any field where AI output can be run and checked automatically (code, SQL, proofs, configs) can use the same loop: one agent builds, one breaks, a coach writes down what it learned, and a gate decides what stays. It's a way to get agents improving themselves without a human in the loop and without touching the weights.
