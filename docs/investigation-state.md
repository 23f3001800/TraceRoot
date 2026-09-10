# Persistent investigation and recovery

TraceRoot runs one Gemini investigator with the same six investigation-only tools.
The model receives the minimal task, bounded observations, a hypothesis registry,
and remaining budgets. It has no checkpoint-writing tool or target write capability.

## State contract

Each run stores an atomic `state.json` beside `initial.json`, `trajectory.jsonl`,
`final.json`, and `summary.json`. The checkpoint is authoritative; the other files
are review views. Checkpoints contain:

- Run/session identity, public snapshot fingerprint, prompt/contract fingerprint,
  model configuration, original task and immutable budgets.
- Ordered tool steps with exact inputs and structured results.
- Hypotheses with stable ID, immutable claim, proposed/supported/rejected status,
  confidence, missing evidence and exact evidence citations.
- The last observation reviewed by the model, public transcript, hypothesis history,
  separate provider/tool failures, pending action and pending model request.
- Cumulative tool/model counts, token usage, active elapsed time, resume count,
  phase, stopping reason and any final report.

Every citation names a successful tool step, a `/data/...` JSON pointer, an exact
excerpt, and the claim it supports. Runtime application errors inside successful
log/test results are evidence; collector, execution and provider failures remain
separate infrastructure records. Hypotheses cannot silently disappear. A changed
explanation gets a new ID; old explanations can be rejected with evidence.

The model must review each new observation before its next action or conclusion.
If a provider failure prevents that review, `reviewed_step` remains behind the
latest tool step; resume sends the unreviewed observation again without rerunning
the tool. Only concise public summaries are recorded, never private thoughts.

## Recovery behavior

The runner checkpoints before dispatching a tool and after receiving its result.
Writes use a temporary file, fsync and atomic replacement. A session lock prevents
concurrent investigators. The kernel releases the lock when a process exits.

Gemini SDK retries are disabled. The runner records every failure and retries
429, transient 5xx responses and timeouts twice by default, waiting 0.5 then 1.0
seconds. Each attempt has a deadline and consumes the same cumulative budget.
400/401 and other nontransient errors are recorded without automatic retry.
Retries repeat the model request, never the previous tool.

After retries are exhausted, the phase is `paused`; `resume` uses the original
run ID, task, model configuration, snapshot, evidence, hypotheses and counters.
Provider downtime between processes does not consume active runtime. Time spent
inside an attempt does. An abruptly interrupted model call conservatively consumes
its reserved timeout, is recorded as interrupted, and can resume with remaining budget.

A tool interrupted before its result was durably saved has an unknown outcome.
Resume marks it `interrupted_tool` and returns `TOOL_FAILURE`; it never automatically
replays the call. This deliberately avoids promising exactly-once external execution.
A disk failure leaves the previous complete checkpoint intact; no later action is
started if its prerequisite checkpoint cannot be saved.

Resume refuses changed snapshots/contracts/models, foreign sessions, malformed
checkpoints, or inactive environments. Completed runs return their saved result
without further tool/model calls. Day 3 artifacts have no checkpoint and cannot be
resumed as Day 4 runs. Do not clean up a paused environment until recovery is finished.

## Stop rules

| Condition | Final status | Phase |
|---|---|---|
| Supported hypothesis and independent cited evidence | ROOT_CAUSE_IDENTIFIED | finished |
| Public reproduction unavailable or observed not reproduced | REPRODUCTION_FAILED | finished |
| No useful evidence path remains, with explicit limitation | INSUFFICIENT_EVIDENCE | finished |
| Provider attempts exhausted | TOOL_FAILURE | paused |
| Tool failure prevents investigation | TOOL_FAILURE | finished |
| Tool outcome unknown after interruption | TOOL_FAILURE | interrupted_tool |
| Cumulative tool, model, context or active-time budget exhausted | MAX_STEPS_REACHED | finished |

A root-cause report must exactly match a supported hypothesis, attach its evidence,
and cite at least two independent families: source, runtime, database or execution.
Confidence cannot bypass these checks. These are provenance and consistency checks;
a human must still evaluate whether the cited observations establish causality.

## Gemini schema compatibility

The API rejected the expanded generation schema with HTTP 400. The provider now
omits bound keywords from the generation grammar while keeping structure, enums,
and required fields. The original local schema still enforces every size/range
limit and tool permission before dispatch. Google documents a supported JSON Schema
subset and recommends application validation: [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

## Verification

`tests/test_recovery.py` covers provider retry/exhaustion, timeout and process-death
recovery, preserved reproduction and hypotheses, evidence validation, cumulative
budgets, snapshot/session mismatch, concurrent execution and failed atomic writes.
Run `.venv/bin/python -m pytest -q` from the TraceRoot directory under WSL/Linux.
