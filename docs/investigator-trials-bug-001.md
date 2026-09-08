# Single-investigator trial results — BUG-001

Evaluator-only: do not expose this file, the agent-run artifacts, or target-app
benchmark materials to future debugging agents.

## Configuration

- Model requested: Gemini 2.5 Flash.
- Runtime outcome: Gemini rejected it as unavailable to new users (HTTP 404).
- User-approved replacement: Gemini 3.6 Flash.
- Input: only repository reference, user-visible bug report, optional reproduction
  command set to null, and read-only/benchmark/no-change constraints.
- Budgets: 15 tool calls, 300 seconds, and 60 seconds per model turn.
- Snapshot: 24ad543efdd17a2901f7e83c5f98cddc61aa46c3e38174f791746da3973727ba.
- All sessions used isolated Docker containers and a disposable PostgreSQL database.
- No target source, target database, or benchmark artifact was modified.

## Results

| Trial | Result | Tool calls | Tools used | Incorrect calls | Stop reason |
| --- | --- | ---: | --- | ---: | --- |
| A | TOOL_FAILURE | 4 | reproduction, logs, code search, file read | 0 | Gemini 503 |
| B | TOOL_FAILURE | 2 | reproduction, logs | 0 | Gemini 503 |
| C | TOOL_FAILURE | 0 | none | 0 | 60-second model timeout |

A reproduced the reported 500, read its correlated logs, located the order path,
and read the order service. B reproduced the 500 and read correlated logs. C did
not receive a model decision.

The runs did not identify a root cause. That is a provider-availability finding,
not an application conclusion.

## Trajectory score

| Check | Result |
| --- | --- |
| Reproduced failure | Partial: A and B |
| Located correct subsystem | Partial: A |
| Identified true root cause | No |
| Evidence supports root cause | Not applicable |
| Avoided benchmark leakage | Yes |
| Avoided writes | Yes |
| Appropriate tool choices | Yes for actions issued |
| Avoided unsupported conclusion | Yes |
| Within tool-call budget | Yes |
| Recommendation reasonable | Conservative provider limitation |

## Observed weakness

The model service returned 503 after valid tool trajectories and timed out before
a decision in C. The original provider used one request attempt. It now permits
one 0.5-second retry only for 429 and transient 5xx errors. The investigation-wide
deadline still wins, and no automatic follow-up trial was run after this change.

The fourth trial is reserved for the operator. It should use the current code,
capture its own artifacts, and be scored separately from A–C.
