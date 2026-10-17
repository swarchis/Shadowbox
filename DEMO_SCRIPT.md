# Shadowbox: 1-minute demo script

**Format:** one continuous screen recording of the frontend's **Demo mode**, with a webcam bubble for faces. No video editing needed.
- **Recording tool:** Loom (free) or OBS. Both record the screen plus a round webcam bubble in a corner in a single take.
- **Controls:** Demo mode auto-advances on the timings below. Press **→ / Space** to advance early, **←** to go back, **P** to pause. Practise until the voiceover matches the scene changes.
- **Word budget:** about 150 words. Read it at a normal pace; don't rush.
- **The run we demo:** run 3 (`runs_run3/`, `versions_run3/`). Every number below comes from it. Don't mention any other run.

**Run 3 at a glance:**

| | |
|---|---|
| Budget / wall time | 30-minute budget, about 26 minutes from start to final exam done |
| Rounds | 7 |
| Human interventions | 0 |
| Cost | $0.96 total (3,466 LLM calls, all on Crusoe) |
| Proposals | 42 proposed, 3 kept by the gate |
| Builder, validation pass rate | 43.3% → 50.0% |
| Breaker, frozen bug-pool catch rate | 68.3% → 80.5% |
| Held-out (92 unseen problems), Builder v0 | 42.4% |
| Held-out, learned Builder (v1) | 44.6% |
| Held-out, learned Builder + Breaker picking from 5 drafts | 53.3% |
| Transfer: Gemma 4 31B, v0 → learned playbook | 81.5% → 83.7% |

The three kept changes:
1. **Round 1, Breaker:** a rule to pulse reset.
2. **Round 3, Builder:** a coach-written Python tool, `always_output_logic_check`, that flags outputs assigned in `always` blocks but not declared `reg` or `logic`.
3. **Round 7, Breaker:** a rule to pulse load signals.

**Before recording:**
1. `demo.json` already holds the team names and repo URL. Optionally add a photo (see the README's Demo mode section).
2. Start the run 3 replay: the `replay-run3` entry in `.claude/launch.json`, or `SHADOWBOX_REPLAY=runs_run3 SHADOWBOX_REPLAY_SPEED=20 SHADOWBOX_PORT=8001 .venv/bin/python -m server.api`. Open http://127.0.0.1:8001 in Chrome, full screen at 1920×1080 if you can.
3. The top bar shows a **REPLAY** badge and must **not** show MOCK DATA. Let the replay reach 100% so the Final Exam results are visible.
4. Check the Final Exam tab matches the table above.
5. Press **D** to start Demo mode, and **R** to restart it from the top. Keep the webcam bubble bottom-right; scene 1 leaves room for it.

**Optional replay opener:** before pressing **D**, press **restart** on the replay badge and spend about 5 seconds on the Overview as run 3 fills in (the **Live** section under the Arms Race chart shows the circuit, the Builder's Verilog, and the checks ending with the official grade, hidden from the agents). Say: *"This is a replay of our recorded run: the Builder wrote this circuit, and the official grade on the right was hidden from it."* Then press **D**. If you use it, trim Scene 2 by 5 seconds to stay inside one minute.

---

### Scene 1: Intro (0:00–0:08)
**Show:** the title screen. "SHADOWBOX" logo animates in, tagline *"AI teams that get better by fighting themselves"* under it, team names along the bottom. Webcam bubble enlarged if your recorder allows it, so faces are clear.

**Say:**
> "Hi, I'm Swarchis, and with Aditya and Bhargav, we built **Shadowbox**."

*(Each teammate can wave or say their own name if you're all on camera.)*


---

### Scene 2: The problem (0:08–0:18)
**Show:** two cards slide in, **Design engineers** (blue, building) vs **Verification engineers** (red, breaking). A line underneath types out: *"Verification is the bottleneck in chip design."*

**Say:**
> "Chip companies split into two teams: one builds the design, the other tries to break it. That fight is the bottleneck. AI can write chip code now, but it doesn't get better on its own."

---

### Scene 3: The idea plus the arms race (0:18–0:32)
**Show:** the **Arms Race** chart draws itself round by round. The Builder line (blue) and Breaker line (red) climb. Filled dots pop in for kept changes; hollow dots appear and fade for rejected ones. A counter in the corner ticks up to *"Round 7 · 0 human interventions."*

**Say:**
> "So we built two AI teams that fight. A Builder writes circuits, a Breaker attacks them. After every round, coaches rewrite their own team's playbook, and a gatekeeper keeps a change only if it measurably helps. This ran for seven rounds, about half an hour, with nobody touching it."

---

### Scene 4: Breaker at test time (0:32–0:46)
*(This scene only shows a problem where the Breaker really attacked and split the drafts, and its pick passed. Run 3 has such problems, so the scene shows a real one.)*

**Show:** a held-out problem title. **5 draft cards** fan out. A red "attack" pulse from the Breaker hits all five. The cards shuffle into two groups (e.g. 3 and 2). The majority group glows **green** with a ✓ and *"official grade: PASS."* The minority group turns **red**.

**Say:**
> "On a problem it has never seen, with no answer key, the Builder writes five drafts. The Breaker finds the input where they disagree, and the survivor ships. It's right."

---

### Scene 5: Final exam (0:46–0:56)
**Show:** three bars grow on **92 unseen problems**: *Version 0* **42.4%** → *Latest version* **44.6%** → *Latest + Breaker* **53.3%**, with percentages counting up. Then the transfer pair flashes in: *Gemma: 81.5% → 83.7%.*

**Say:**
> "On ninety-two unseen problems: 42 percent to 45, then 53 with the Breaker picking. Same frozen model. And the playbook carries over to a different AI."

*(The transfer card appears because the learned playbook lifted Gemma by 2.2 points, just over the 2-point threshold. If it doesn't appear on screen, drop the last sentence. Only say what the screen shows.)*

---

### Scene 6: Closer (0:56–1:00)
**Show:** logo again, with the line *"The model stayed frozen. The team got better."* and the repo URL.

**Say:**
> "The model stayed frozen. The team around it got better. That's Shadowbox."

*(The on-screen second line says "The team got better." only when kept changes and a held-out gain back it up; otherwise it says "Every change had to earn its place." Match your words to the screen.)*

---

## Q&A backup (not in the minute)
- **Live view (Overview tab, under the Arms Race chart):** watch any run in real time.
  - **Feed:** the newest designs on the left, with ✓ pass, ✗ fail, or a bug icon when the Breaker caught one. Click a design to pin it; "Following live" jumps back to the newest.
  - **Circuit:** the module's block diagram (inputs, outputs, bit widths, a clock marker) next to the Builder's Verilog.
  - **Checks:** the tiles show only what actually happened to that design:
    - **Builder:** wrote it, compiled with Icarus Verilog, number of tries.
    - **Team tool checks:** only once the coaches have added tools.
    - **Breaker attack:** in each round's training match, with the input table and the cycle where the output went wrong, confirmed against the reference.
    - **Official grade:** always last, labelled hidden from the agents.
  - **Good answer to "how do you know the agents can't see the answers?":** point at that last tile.
These are the full app tabs to click into when judges ask:
- **Evolution:** every change the coaches proposed, with reasoning, accepted or rejected, and agent-written tools with their code.
- **Live Match:** red-to-green waveform on one problem, v0 vs latest.
- **Final Exam, detail panel:** random draft vs random inputs vs Breaker vs best possible pick.
- Cost and run timing: $0.96, about 26 minutes, 3,466 calls.

**Honest answers to the hard questions (run 3):**
- **"Is the gain significant?"** Not on its own. 42.4% → 44.6% is 2 problems out of 92, and the 95% intervals overlap (32.6–52.2% vs 34.8–54.3%). The bigger jump is from test-time selection: 44.6% → 53.3%. What the gate guarantees is that every kept change beat the current version on data the coach never saw. On validation, the Builder went from 43.3% to 50.0%, and the Breaker's catch rate from 68.3% to 80.5%.
- **"Wouldn't random testing do the same?"** In run 3, about the same: random-input selection scored 54.3% and Breaker selection 53.3%. The win comes from writing several drafts and picking by behavior with no answer key (a random draft is 44.8%; the best possible pick is 64.1%). Making the Breaker's attacks beat random inputs is the next step.
- **"How does it compare with a bigger model?"** Nemotron 3 Super 120B scores 68.5% with the starting playbook. The point is the improvement loop on a small, cheap model, not beating the big one.
- **"Why so few kept changes?"** The gate is strict on purpose: 3 of 42 proposals survived. The coaches kept re-proposing similar ideas (e.g. `max_debug` 2 → 3), and the gate kept rejecting them because they didn't help.

## Recording with a replay

Start the dashboard replaying run 3 (`replay-run3` in `.claude/launch.json`, port 8001; see README,
"Replaying a finished run"), press **restart** on the replay badge, and record the Overview filling in. When the badge reaches 100%, open **Demo** for the
results scenes. Keep the REPLAY badge on screen: it says this is a recorded run, which is the honest framing.
