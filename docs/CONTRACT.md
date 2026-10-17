# Shadowbox data contract

The engine writes plain JSON files. The FastAPI server (`server/api.py`) reads them and serves the REST API below. The React app (`web/`) only talks to the REST API. All three must agree on these shapes; if you change one, update this file.

Conventions:
- Pass rates are fractions in [0, 1]. The UI formats them as percentages.
- `mode` is `"mock"` or `"real"`. In mock mode every screen shows a visible **MOCK DATA** badge.
- Timestamps are ISO-8601 UTC strings.
- Verilog bit values in traces are binary strings (may contain `x`/`z`), e.g. `"0101"`.

## Directory layout written by the engine

```
RUNS_DIR/                       runs/ (real) or runs_mock/ (mock)
  state.json                    live status of the whole run  (= /api/state body)
  series.json                   arms-race points + changes    (= /api/series body)
  events.jsonl                  one JSON object per line, append-only (seq = 0-based line index)
  ledger.jsonl                  one line per LLM call (cost tracking)
  baseline/val_v0.json          Builder v0 results on validation
  bug_pool.json                 frozen bug pool
  round_<n>/match.json          the round's train match       (= /api/rounds/{n}/match body)
  round_<n>/builder_gate.json   Builder proposals + gate result (internal; lineage.json is the public view)
  round_<n>/breaker_gate.json   Breaker proposals + gate result (internal)
  round_<n>/done.json           marker: round complete
  final/final.json              final exam numbers            (= /api/final body)
  final/selection_examples.json test-time selection examples  (= /api/selection-examples body)
  final/demo_cases.json         v0-vs-vBest live-match cases  (= /api/demo-cases body)
VERSIONS_DIR/                   versions/ (real) or versions_mock/ (mock)
  lineage.json                  every proposed change          (= /api/lineage body)
  builder/current.json          {"version": n}
  builder/v<n>/playbook.json
  builder/v<n>/tools/<name>.py
  breaker/...                   same layout
ROOT/demo.json                  presenter settings             (= /api/demo-config body)
```

Most endpoints serve these files directly. The server only derives `/api/rounds` (by scanning `round_<n>/`), `/api/playbooks/*` (by scanning `VERSIONS_DIR`) and `/api/events` (by reading `events.jsonl`). Files may be mid-write while the engine runs: the engine writes them atomically (temp file + rename), and the server treats any unreadable file as missing.

## REST API

All endpoints are `GET` and return JSON. Missing data returns an empty-but-valid shape (never 404) so the UI can render "waiting for first round".

### `GET /api/state`
```json
{
  "mode": "mock",
  "status": "running",            // idle | running | finished | error | stopped
  "phase": "round",               // setup | bug_pool | round | final | done
  "round": 3,
  "step": "builder_gate",         // match | builder_coach | builder_gate | breaker_coach | breaker_gate | done
  "message": "Gating 1 Builder candidate on 30 validation problems",
  "started_at": "2026-10-16T22:00:00Z",
  "updated_at": "2026-10-16T22:31:05Z",
  "deadline_at": "2026-10-16T23:00:00Z",   // null if no time budget
  "spend_usd": 12.41,
  "spend_cap_usd": 45.0,
  "llm_calls": 812,
  "human_interventions": 0,
  "builder_version": 2,
  "breaker_version": 1,
  "splits": {"train": 30, "val": 30, "test": 92}
}
```

### `GET /api/series` (Arms Race chart)
One point per completed round, plus round 0 = baseline.
```json
{
  "points": [
    {"round": 0, "builder_val_pass": 0.43, "breaker_pool_catch": 0.52, "builder_train_pass": 0.40, "builder_hard_pass": 0.37,
     "builder_version": 0, "breaker_version": 0},
    {"round": 1, "builder_val_pass": 0.50, "breaker_pool_catch": 0.52, "builder_train_pass": 0.47, "builder_hard_pass": 0.43,
     "builder_version": 1, "breaker_version": 0}
  ],
  "changes": [
    {"round": 1, "team": "builder", "accepted": true,  "summary": "Use non-blocking assignments in clocked blocks", "net_flips": 4},
    {"round": 1, "team": "breaker", "accepted": false, "summary": "Hold reset for 3 cycles", "net_flips": 1}
  ]
}
```
`builder_val_pass` is the current Builder's validation pass rate after the round. `breaker_pool_catch` is the current Breaker's catch rate on the frozen bug pool after the round.

### `GET /api/lineage`
```json
{
  "entries": [
    {
      "id": "r1-builder-c0",
      "round": 1,
      "team": "builder",                  // builder | breaker
      "change_type": "rule_add",          // prompt_edit | rule_add | rule_remove | tool_add | tool_remove | param
      "summary": "Use non-blocking assignments in clocked always blocks",
      "reasoning": "5 of 14 train failures (Prob031, Prob041, ...) used blocking '=' inside always @(posedge clk) ...",
      "evidence_problems": ["Prob031_dff", "Prob041_dff8r"],
      "score_before": 0.43,
      "score_after": 0.53,
      "gained": ["Prob034_dff8", "Prob046_dff8p", "Prob047_dff8ar", "Prob073_dff16e"],
      "lost": [],
      "net_flips": 4,
      "accepted": true,
      "from_version": 0,
      "new_version": 1,                   // null if rejected
      "tool_name": null,                  // set for tool_add / tool_remove
      "cost_usd": 0.92,
      "ts": "2026-10-16T22:14:00Z"
    }
  ]
}
```

### `GET /api/rounds`
```json
{"rounds": [{"round": 1, "complete": true, "builder_version": 0, "breaker_version": 0,
             "train_pass": 0.40, "hard_pass": 0.37, "bugs_found": 9, "subtle_bugs": 1, "problems": 30}]}
```

### `GET /api/rounds/{n}/match`
```json
{
  "round": 1, "builder_version": 0, "breaker_version": 0,
  "summary": {"train_pass": 0.40, "hard_pass": 0.37, "bugs_found": 9, "subtle_bugs": 1, "problems": 30},
  "problems": [
    {
      "problem_id": "Prob031_dff",
      "spec": "I would like you to implement ...",
      "is_sequential": true,
      "official": {"passed": false, "kind": "mismatch", "mismatches": 12, "samples": 200},
      "hard_pass": false,
      "build": {"code": "module TopModule(...)...", "compiled": true, "attempts": 2,
                "steps": [{"agent": "writer", "summary": "Wrote first draft"}, {"agent": "debugger", "summary": "Fixed port width"}],
                "tool_reports": [{"tool": "lint_check", "fired": true, "findings": ["blocking assignment in clocked block"]}]},
      "attack": {"stimulus_cycles": 24, "valid_bug": true, "caught_by_official": true,
                 "first_mismatch": {"cycle": 3, "phase": "post", "signal": "q", "expected": "1", "got": "0", "inputs": {"d": 1}}}
    }
  ]
}
```

### `GET /api/playbooks/{team}`
```json
{"team": "builder", "current": 2, "versions": [{"version": 0, "parent": null, "rules": 0, "tools": 0, "created_round": null}]}
```

### `GET /api/playbooks/{team}/{version}`
```json
{"version": 2, "parent": 1, "team": "builder", "prompts": {"writer": "..."}, "rules": ["..."], "tools": ["lint_check"],
 "params": {"max_debug_attempts": 2}, "tool_sources": {"lint_check": "def run(spec, verilog, ports): ..."},
 "tool_stats": {"lint_check": {"runs": 60, "fired": 14, "born_round": 2}}}
```

### `GET /api/final` (Final Exam)
Every metric is optional; missing ones are `null` and the UI hides that bar. Each metric may also carry `"errors": k`, the number of problems excluded because their model calls failed (API errors are never counted as wrong answers). `complete` is `false` while the exam is still running or after a hard stop at the time limit (then `notes[0]` explains). `n_drafts` is how many test-time drafts per problem were used (3-5, fewer when time ran short).
```json
{
  "complete": true,
  "test_problems": 92,
  "n_drafts": 5,
  "metrics": {
    "v0":                {"label": "Version 0", "pass": 0.41, "ci": [0.31, 0.51], "n": 92},
    "vbest":             {"label": "Latest version", "pass": 0.55, "ci": [0.45, 0.65], "n": 92},
    "vbest_selection":   {"label": "Latest + Breaker", "pass": 0.62, "ci": [0.52, 0.71], "n": 92},
    "random_pick":       {"label": "Random draft", "pass": 0.50, "ci": null, "n": 92},
    "random_input_sel":  {"label": "Random-input selection", "pass": 0.56, "ci": null, "n": 92},
    "breaker_v0_sel":    {"label": "Selection with Breaker v0", "pass": 0.58, "ci": null, "n": 92},
    "ceiling":           {"label": "Best possible pick", "pass": 0.70, "ci": null, "n": 92},
    "ultra":             {"label": "Nemotron Ultra (v0 playbook)", "pass": 0.60, "ci": [0.50, 0.70], "n": 92},
    "transfer_v0":       {"label": "Gemma + v0 playbook", "pass": 0.38, "ci": null, "n": 92},
    "transfer_vbest":    {"label": "Gemma + learned playbook", "pass": 0.47, "ci": null, "n": 92},
    "ablation_nano_coach": {"label": "Gain with Nano coach", "pass": 0.06, "ci": null, "n": 20},
    "ablation_main_coach": {"label": "Gain with main coach", "pass": 0.10, "ci": null, "n": 20}
  },
  "builder_versions": {"v0": 0, "vbest": 4},
  "breaker_versions": {"v0": 0, "vbest": 3},
  "cost_usd": 9.80,
  "notes": ["CIs are 95% bootstrap over problems."]
}
```

### `GET /api/selection-examples`
Test-time selection on held-out problems. Use the first example where `chosen_correct` is true and at least one draft was wrong for the demo.
```json
{
  "examples": [
    {
      "problem_id": "Prob112_always_case2",
      "spec": "...",
      "drafts": [
        {"label": "d0", "code": "...", "compiled": true, "official_pass": true},
        {"label": "d1", "code": "...", "compiled": true, "official_pass": false}
      ],
      "groups": [["d0", "d2", "d4"], ["d1", "d3"]],
      "chosen_group": 0,
      "chosen_label": "d0",
      "chosen_correct": true,
      "decided_by": "majority",          // majority | judge | single | none
      "judge_reasoning": null,
      "disputed": {"cycle": 2, "phase": "comb", "inputs": {"in": 5}, "outputs": {"d0": {"pos": "010"}, "d1": {"pos": "000"}}},
      "stimulus_cycles": 18
    }
  ]
}
```

### `GET /api/demo-cases`
Live Match cases: problems where Builder v0 failed and vBest passed, with a waveform trace from the Breaker's attack against v0.
If the Builder never improved, the engine falls back to cases where v0 failed and the Breaker-selected draft passed; then `vbest.version` is the string `"selection"` (label it "Latest + Breaker") and `explanation.round` is `null`. `explanation` may also be `null`.
```json
{
  "cases": [
    {
      "problem_id": "Prob047_dff8ar",
      "spec": "...",
      "v0": {"version": 0, "code": "...", "official_pass": false},
      "vbest": {"version": 4, "code": "...", "official_pass": true},
      "explanation": {"round": 2, "summary": "Handle asynchronous reset in the sensitivity list", "reasoning": "..."},
      "trace": {
        "signals": [{"name": "clk", "kind": "clock"}, {"name": "areset", "kind": "input", "width": 1},
                    {"name": "q", "kind": "output", "width": 8}],
        "rows": [
          {"t": 0, "inputs": {"areset": "1", "d": "00000011"}, "expected": {"q": "00000000"}, "v0": {"q": "xxxxxxxx"}, "vbest": {"q": "00000000"}}
        ],
        "first_mismatch_row": 0
      }
    }
  ]
}
```

### `GET /api/demo-config`
Static presenter settings from `demo.json` at the repo root (team names, tagline).
```json
{"project": "Shadowbox", "tagline": "AI teams that get better by fighting themselves",
 "team": [{"name": "Your Name", "photo": null}], "repo_url": "https://github.com/..."}
```

### `GET /api/events?since=<n>`
```json
{"events": [{"seq": 41, "ts": "...", "type": "gate_result", "round": 2, "team": "builder", "message": "Accepted: +4 net"}], "next": 42}
```

## Engine output beyond the examples (all optional for the UI)

The examples above show the core fields. The engine also writes these; the UI tolerates all of them (`web/src/lib/normalize.ts`):

- **`/api/state`**
  - `step` can also be `baseline`, `bug_pool`, `breaker_baseline`, `final`, `selection`, `demo_material`.
  - `status` can also be `stopped` (spend cap or Ctrl-C) and `error` (fatal API error or crash, with the reason in `message`).
- **`/api/series`**
  - `gate_margin` is the net flips a change needs to be kept (3 by default).
  - `points[*].builder_val_pass` / `breaker_pool_catch` may be `null` before scoring.
  - `changes[*].invalid` is `true` for proposals rejected before testing.
- **`/api/lineage` entries**
  - `invalid_reason`: why a proposal was rejected without testing.
  - `rule_text`, `tool_name`.
  - `errors`: items excluded because of API errors.
  - `net_flips` and `score_after` are `null` when the proposal was not tested.
- **`/api/selection-examples`**
  - `decided_by` can also be `fallback`: the Breaker produced no usable stimulus, so the first compiling draft was taken.
  - `chosen_group` and `chosen_label` are `null` when no draft compiled.
- **`/api/state`**
  - `human_interventions` is the number of times a person restarted or resumed the run by hand.
  - While it works, the engine refreshes `updated_at` at least every 30 s. The UI treats a `running` state that hasn't been updated for 5 minutes as stopped.
- **`/api/series`**: `distinct_bugs` / `distinct_subtle_bugs` count unique buggy designs (problem + code) the Breaker exposed across all rounds. The same unchanged design re-attacked in several rounds counts once.
- **`/api/demo-cases` `trace.source`**: `"breaker"` when the waveform replays the Breaker's own attack, or `"random"` when that attack didn't expose v0's bug and random inputs are shown instead. The UI labels it accordingly. Breaker-exposed cases are listed first.
- **`/api/final`**: the main bars and the selection detail rows are computed on one common set of problems, excluding any problem where a needed model call failed. `notes[0]` says how many were excluded.
- **`/api/demo-cases` `explanation`**
  - `kind`: `"builder"` (v0 failed, the latest version passed) or `"selection"` (fallback case).
  - `changes`: every playbook change kept between v0 and the latest, as `[{round, summary}]`.
  - The engine does not claim which single change fixed a given problem.
- **`/api/playbooks/{team}/{version}` `tool_stats[*]`**: `runs`, `fired`, `errors`, `born_round` (may be `null`).
- **`/api/events`**: events can carry extra keys such as `accepted` or `tag`. Event `type`s include `run_start`, `baseline`, `bug_pool`, `match_start`, `match_done`, `proposal_invalid`, `gate_result`, `gate_skipped`, `round_done`, `time_budget`, `hard_stop`, `final_start`, `final_step`, `final_done`, `llm_retry`, `llm_truncated`, `llm_error`, `api_errors`, `retry_errors`, `coach_parse`, `spend_cap`, `fatal`, `crash`, `v0_refreshed`.
