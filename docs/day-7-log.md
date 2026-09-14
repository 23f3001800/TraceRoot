# Day 7 Log

## 2026-09-14 — Reliability implementation

- Inspected the Day 5 graph, Day 4 state, Docker runtime, tools, and tests.
- Attempted `apply_patch`; the workspace patch helper failed during sandbox setup. Used a scoped PowerShell/Python fallback to write the same reviewed edits.
- Added controlled read-only configuration and Git evidence tools.
- Added reproduction input, attempt, and consistency fields.
- Added `PROVIDER_FAILURE` and fixed its checkpoint resume gate.
- Required runtime/reproduction plus confirming subsystem evidence for root-cause reports.
- Added focused tool and recovery tests.
- Focused verification passed: `24 passed`.
- Full verification remains blocked only by missing optional `google.genai` in WSL.

## 2026-09-14 — Live recovery and BUG-003

- Docker server health check passed (`29.1.3`). The first BUG-003 setup failed during database-role setup; a retry completed setup, reproduction, and runtime-log collection.
- Restored the isolated `.venv` launcher after WSL system Python lacked `google.genai`.
- BUG-003 run `cafa8c1a270d40e48efcb3036dbd13eb`: reproduction confirmed, two read-only tools ran, then Gemini produced three invalid structured decisions. Final status: `TOOL_FAILURE`, limitation `invalid_decisions`.
- This is a reasoning/structured-output gap, not missing application evidence or a provider failure.
- Improved Docker failure messages to identify the failed operation without exposing secrets.
