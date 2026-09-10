# Day 4 checklist: state, hypotheses and recovery

## Completed implementation

- [x] Investigation state is structured and stored atomically in `state.json`.
- [x] The checkpoint persists task, snapshot and prompt fingerprints, budgets,
  transcript, ordered observations, model/tool counts, usage and stop state.
- [x] Hypotheses have a stable ID, claim, status, confidence, missing evidence
  and concrete citations. Proposed claims may be refined; supported and rejected
  claims remain auditable history.
- [x] Every evidence citation uses a successful tool step, `/data/...` pointer and
  exact excerpt. Root cause needs a matching supported hypothesis and independent
  evidence families. Confidence never establishes a root cause by itself.
- [x] Provider failures are separate from application evidence and tool failures.
- [x] Retries have bounded 0.5/1.0-second backoff. A retry repeats only the model
  request; it never repeats a saved tool result or successful reproduction.
- [x] A paused checkpoint resumes with the original task, snapshot, model contract
  and cumulative budgets. Completed runs do not run again.
- [x] Unknown interrupted tool calls are not replayed. Snapshot drift, foreign
  checkpoints, malformed state and concurrent investigators fail closed.
- [x] Explicit statuses cover supported root cause, unavailable reproduction,
  insufficient evidence, provider/tool failure and exhausted budgets.
- [x] No target source or database write capability was added.

## Verification

`92 passed, 4 skipped`:

- Checkpoint atomicity and session locking.
- Provider timeout/503 retry, exhausted retry and resume.
- Completed reproduction is preserved through resume.
- Interrupted model/tool behavior and immutable cumulative budgets.
- Hypothesis add, support, reject and evidence-linked refinement.
- Invalid citations, fabricated evidence and unsupported root-cause reports.
- Timeout-to-root-cause recovery under the real investigation state machine.

## Live BUG-001 recovery trial

Session `3275a3e49c2e`, run `23907e7c7f784e46adb39bb3f8b2ecaf` remains paused
and resumable. It has three successful read-only calls: reproduction, application
logs and code search. Reproduction confirmed 500; logs identified the PostgreSQL
check violation; the model's persisted hypothesis connected the bulk discount to
`order_total_consistent`. The run resumed twice without rerunning any completed
call. Gemini then returned eleven transient 503 failures across its bounded retry
attempts, so TraceRoot returned `TOOL_FAILURE` instead of fabricating a conclusion.

The deterministic recovery test completes an evidence-backed root-cause report
through the same state machine without patching. The live model completion remains
pending Gemini availability; resume it with the command in
[run and resume](run-single-investigator.md). Keep its disposable session active
until it reaches a final status or you intentionally clean it up.
