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

## 2026-09-14 — Structured decision repair

- Inspected saved rejection messages for BUG-004: Gemini produced IDs such as `h-1`, while persisted state requires canonical `H1`.
- Added a narrow provider-boundary normalizer for only `H`, optional separator, and 1–99. Arbitrary IDs remain rejected.
- Corrected the investigator prompt to describe the registered read-only tools and require `H1`, `H2`, and so on.
- Added a normalization regression test; focused suite passed: `8 passed`.


## 2026-09-14 ? BUG-003 rerun

- After hypothesis-ID normalization, BUG-003 advanced from two to seven successful evidence calls.
- Gemini then exhausted bounded provider retries. TraceRoot returned `PROVIDER_FAILURE`, retained seven steps and hypothesis `H1`, and did not rerun reproduction.
- The disposable benchmark runner incorrectly cleaned the environment after a paused provider failure. Updated the runner to preserve that session for resume.
- Docker setup remains intermittently flaky at `exec`; bounded stderr is now recorded in its operator error.

## 2026-09-14 — BUG-004 resume

- BUG-004 reproduced and found the runtime error `Client.__init__() got an unexpected keyword argument 'proxies'`.
- The model proposed the dependency/API mismatch hypothesis with concrete reproduction and log citations.
- Resume started at saved step 3; reproduction did not run again.
- Seven cumulative provider failures then exhausted bounded retries. The checkpoint remains paused and resumable.
- Deferred BUG-005 and BUG-006 live calls because the same provider outage would produce no new evidence.
