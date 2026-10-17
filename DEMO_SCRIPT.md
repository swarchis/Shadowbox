# Shadowbox: 1-minute demo script

**Format:** one continuous screen recording of the frontend's **Demo mode**, with a webcam bubble for faces. No video editing needed.
- **Recording tool:** Loom (free) or OBS. Both record the screen plus a round webcam bubble in a corner in a single take.
- **Controls:** Demo mode auto-advances on the timings below. Press **→ / Space** to advance early, **←** to go back, **P** to pause. Practise until the voiceover matches the scene changes.
- **Word budget:** about 150 words. Read it at a normal pace; don't rush.
- **[X] / [Y] / [Z]:** fill these in from the real run. The Final Exam scene shows the live numbers, so read them off the screen.

**Before recording:**
1. The real run has finished. The top bar must **not** show a MOCK DATA badge.
2. Fill in your names, photos and repo URL in `demo.json` (see the README's Demo mode section).
3. Start the server with `.venv/bin/python -m server.api` and open http://127.0.0.1:8000 in Chrome, full screen at 1920×1080 if you can.
4. Read the real numbers off the Final Exam tab and put them in place of [X]/[Y]/[Z] below.
5. Press **D** to start Demo mode, and **R** to restart it from the top. Keep the webcam bubble bottom-right; scene 1 leaves room for it.

**Optional live opener (only if a run is going while you present or record):** before pressing **D**, spend about 5 seconds on the Overview tab's **Live** section (under the Arms Race chart). It shows what the agents are building right now: the circuit as a block diagram, the Builder's Verilog, and the checks it just went through, ending with the official grade (hidden from the agents). Say: *"This is running live right now: the Builder just wrote this circuit, and the official grade on the right is hidden from it."* Then press **D**. If you use it, trim Scene 2 by 5 seconds to stay inside one minute.

---

### Scene 1: Intro (0:00–0:08)
**Show:** the title screen. "SHADOWBOX" logo animates in, tagline *"AI teams that get better by fighting themselves"* under it, team names along the bottom. Webcam bubble enlarged if your recorder allows it, so faces are clear.

**Say:**
> "Hi, I'm [Name], and with [Teammate], [Teammate] and [Teammate], we built **Shadowbox**."

*(Each teammate can wave or say their own name if you're all on camera.)*

---

### Scene 2: The problem (0:08–0:18)
**Show:** two cards slide in, **Design engineers** (blue, building) vs **Verification engineers** (red, breaking). A line underneath types out: *"Verification is the bottleneck in chip design."*

**Say:**
> "Chip companies split into two teams: one builds the design, the other tries to break it. That fight is the bottleneck. AI can write chip code now, but it doesn't get better on its own."

---

### Scene 3: The idea plus the arms race (0:18–0:32)
**Show:** the **Arms Race** chart draws itself round by round. The Builder line (blue) and Breaker line (red) climb. Filled dots pop in for kept changes; hollow dots appear and fade for rejected ones. A counter in the corner ticks up: *"Round 5 · 0 human interventions."*

**Say:**
> "So we built two AI teams that fight. A Builder writes circuits, a Breaker attacks them. After every round, coaches rewrite their own team's playbook, and a gatekeeper keeps a change only if it measurably helps. This ran for an hour with nobody touching it."

---

### Scene 4: Breaker at test time (0:32–0:46)
*(This scene only shows a problem where the Breaker really attacked and split the drafts, and its pick passed. If the run has none, it shows a placeholder; then cut this line from the voiceover.)*

**Show:** a held-out problem title. **5 draft cards** fan out. A red "attack" pulse from the Breaker hits all five. The cards shuffle into two groups (e.g. 3 and 2). The majority group glows **green** with a ✓ and *"official grade: PASS."* The minority group turns **red**.

**Say:**
> "On a problem it has never seen, with no answer key, the Builder writes five drafts. The Breaker finds the input where they disagree, and the survivor ships. It's right."

---

### Scene 5: Final exam (0:46–0:56)
**Show:** three bars grow on **unseen problems**: *Version 1* → *Latest version* → *Latest + Breaker*, with percentages counting up. If transfer is strong, a fourth pair flashes in: *Gemma: before / after.*

**Say:**
> "On unseen problems: [X]% to [Y]%, then [Z]% with the Breaker. Same frozen model. And the playbook transfers to a different AI."

*(Drop the last sentence if the transfer card isn't shown; it only appears when the learned playbook clearly helps the other model. Drop "then [Z]% with the Breaker" if that bar isn't higher than the latest-version bar. Only say what the screen shows.)*

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
- **Final Exam, detail panel:** random draft vs random inputs vs Breaker vs best possible pick (answers "wouldn't random testing do the same?").
- Distillation ablation, cost, and run timing.
