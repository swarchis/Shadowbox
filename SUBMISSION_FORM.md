# Submission form answers (draft)

All numbers are from run 3. Fill in the video link, and edit the feedback answers into your own words.

**Team name:** Shadowbox

**Team members:** Swarchis Kulkarni, Aditya Singampalli, Bhargav Nemani

**Project description:**

Shadowbox is a pair of AI agent teams that make each other better at chip design. The Builder team writes Verilog from English specs in NVIDIA's VerilogEval benchmark, and the Breaker team writes input sequences that try to expose bugs in those designs. After every round, each team's coach reads the results and proposes a change to its own playbook: a prompt, a rule, a new Python checking tool, or a setting. A gatekeeper tests every proposal on data the coach never saw and keeps it only if it measurably helps. The model weights never change; only the team around the model rewrites itself.

At test time the two teams work together without an answer key. The Builder writes five drafts, the Breaker searches for inputs where they disagree, and the majority behavior ships.

The problem: verification is the bottleneck in chip design, and AI that writes hardware code doesn't get better on its own. In our recorded run (7 rounds, about 26 minutes, 0 human interventions, $0.96 total), the gate kept 3 of 42 proposals. One was a coach-written lint tool that catches outputs assigned in `always` blocks without a `reg` or `logic` declaration. On validation, the Builder went from 43.3% to 50.0% and the Breaker's bug-catch rate from 68.3% to 80.5%. On 92 held-out problems no agent ever saw, the pass rate went from 42.4% to 44.6% with the learned playbook, and to 53.3% with Breaker-assisted selection, all on the same frozen Nemotron model. The learned playbook also carried over to a different model: Gemma 4 31B went from 81.5% to 83.7%.

**Public GitHub repository:** https://github.com/swarchis/Shadowbox

**Public demo video:** _(your YouTube link)_

**Which problem statement are you submitting to?** Version N+1

**Are you submitting for NVIDIA's Best Use of Nemotron?** Yes

**Are you submitting for NVIDIA's Best Use of NemoClaw & OpenShell?** No

**Did you use NVIDIA tools for your project?** Yes. Nemotron runs the whole system: Nemotron 3.5 Lightning 30B-A3B is the worker for both teams, Nemotron 3 Super 120B-A12B is both coaches and the big-model baseline, and Nemotron 3 Nano 30B-A3B is the judge for test-time selection. The benchmark is NVIDIA's VerilogEval v2.

**Did you use You.com tools for your project?** No

**Describe your use of Crusoe Managed Inference to build the submitted project:**

Every LLM call in Shadowbox goes through Crusoe Managed Inference's OpenAI-compatible endpoint. The run used 3,466 calls for $0.96. One client (`engine/llm.py`) wraps the `openai` SDK pointed at Crusoe. It logs every call's tokens and cost to a ledger, enforces a spend cap, retries rate limits with backoff, caches responses so an interrupted run resumes without re-billing, and controls reasoning effort per role. We served four models from Crusoe in one run:
- Nemotron 3.5 Lightning as the worker for the Builder and Breaker
- Nemotron 3 Super as the coaches and the big-model baseline
- Nemotron 3 Nano as the judge
- Gemma 4 31B for the transfer test

Spreading roles across models also spread per-model rate limits. Before a run, a `check` command lists the models available to the key, pings each one, and verifies the configured IDs.

**Feedback on Crusoe products:** _(edit into your own words)_

The OpenAI-compatible API made setup quick: we pointed the standard `openai` SDK at the endpoint and everything worked, including listing models to validate IDs. Having Nemotron, Gemma and others behind one key and one endpoint made it easy to give each agent role its own model. The prices let us run a full 7-round self-improvement loop plus a 92-problem final exam for under a dollar. Rate limits were the main friction: with a few dozen parallel calls we hit many 429s and had to build throttling and retries ourselves. Clearer published per-model limits, or rate-limit headers, would help. Nemotron 3 Ultra wasn't available to our key, so we used Super as the big-model baseline.

**Feedback on partner products:** _(edit into your own words)_

Nemotron 3.5 Lightning was a good worker model for an improvement loop: fast and cheap, and still able to write compilable Verilog. In a head-to-head on 30 training problems it beat Nemotron 3 Nano (16/30 vs 13/30) while being faster and cheaper. Nemotron 3 Super with low reasoning effort gave useful coach proposals, including a working Python lint tool that passed the gate. NVIDIA's VerilogEval gave us specs, reference designs and official testbenches, which made objective, held-out scoring possible. We didn't use NemoClaw/OpenShell or You.com in this build. We sandboxed agent-written tools with macOS `sandbox-exec` instead, and OpenShell would be the natural next step there.
