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


## 2026-09-14 ? OpenRouter provider

- Detected `OPENROUTER_API_KEY` by name only; key material was not read into logs.
- Added OpenRouter OpenAI-compatible JSON provider, using `OPENROUTER_MODEL` when supplied and `google/gemini-2.5-flash` otherwise.
- Provider factory prefers OpenRouter when configured.
- Added focused provider tests: `8 passed`.


## 2026-09-14 ? OpenRouter structured output

- OpenRouter completed model calls but returned actions outside the local union schema.
- Switched its request from generic JSON mode to OpenAI-compatible strict JSON Schema mode.
- Extended the provider regression test to assert schema mode.

## 2026-09-14 — Parallel BUG-005 and BUG-006

- BUG-005 resumed from step 2 without replaying reproduction. Its supported hypothesis remains database QueuePool exhaustion, cited to the 500 reproduction and TimeoutError log entry. It paused after OpenRouter provider failures.
- BUG-006 reproduced and collected runtime logs in parallel, then paused on its first provider failure. No hypothesis was persisted yet.
- Both checkpoints remain resumable and preserve their disposable environments.

## 2026-09-14 — Final six-run evaluation

- Recorded the best observed result for BUG-001 through BUG-006 in `docs/day-7-final-evaluation.md`.
- Chose one future specialist: Evidence Auditor. It independently validates citations and root-cause sufficiency but cannot investigate or write.
- Deferred code, database, and fix agents: present evidence does not justify them.

## 2026-09-14 — Evidence Auditor implementation

- Replaced the graph’s combined evaluation node with a constrained Evidence Auditor node.
- Added persistent audit history and migration defaults for existing Day 4/5 checkpoints.
- Auditor receives evidence only and cannot choose tools.
- Added structured SUPPORTED, INSUFFICIENT, and CONTRADICTED routing.
- Focused graph, recovery, and provider tests passed: `25 passed`.

## 2026-09-14 — Auditor live comparison attempt

- Resumed BUG-006 under the Investigator-plus-Auditor graph.
- The provider failed before the next investigator decision, so the Auditor was not called.
- Reproduction and logs remain preserved at step 2; the run is resumable and did not replay tools.

## 2026-09-15 — BUG-006 second auditor resume

- Resumed BUG-006 from step 2 under the Investigator-plus-Auditor graph.
- OpenRouter failed before the next investigator decision; Auditor was not called.
- Checkpoint remains paused and resumable. Reproduction and runtime logs were not repeated.


## 2026-09-15 ? Direct Gemini selection

- Confirmed both Gemini and OpenRouter keys are configured without reading key values.
- Added `TRACEROOT_PROVIDER=gemini` to select the direct Gemini provider when OpenRouter is also configured.

## 2026-09-15 — Gemini with OpenRouter fallback

- Added `TRACEROOT_PROVIDER=fallback`: direct Gemini is primary and OpenRouter is used only after a retryable primary failure.
- Explicit `gemini` and `openrouter` modes remain available.
- Successful fallback is retained in provider-failure history for auditability.
- Focused provider and graph verification passed: `9 passed`.

## 2026-09-15 — BUG-006 Gemini fallback run

- Gemini-primary/OpenRouter-fallback resumed BUG-006 at step 2 and advanced it to four evidence calls without replaying reproduction or logs.
- The investigator recorded hypothesis H1: successful payment handling does not persist `paid` status to the order.
- Provider failure occurred before the Evidence Auditor node; checkpoint remains resumable at step 4.

## 2026-09-15 — OpenRouter allowance and free fallback

- Provider history showed OpenRouter HTTP 402, while Gemini returned 503.
- Read-only OpenRouter key metadata confirmed the new key is valid, free-tier, and has no paid allowance configured.
- Verified `google/gemini-2.5-flash` is API-compatible but paid; it requires available OpenRouter credit.
- Set local fallback model to `openrouter/free`, which advertises structured-output support.
- A minimal strict JSON-schema request completed successfully through `openrouter/free`.


## 2026-09-15 ? OpenRouter provider diagnosis

- Read-only key metadata returned HTTP 200: valid key, free tier, zero usage and no paid allowance.
- OpenRouter returned HTTP 402 for paid `google/gemini-2.5-flash`; this is billing, not model compatibility.
- `google/gemini-2.5-flash` supports strict JSON Schema on OpenRouter.
- `openrouter/free` returned a malformed structured response despite HTTP 200, so it is unsuitable for the strict agent contract.
- Configured an explicitly structured-output-compatible free fallback model (`nex-agi/nex-n2.5-mini:free`) for local testing.
- OpenRouter HTTP-200 malformed structured responses now classify as retryable `invalid_json`, not provider HTTP failures.

## 2026-09-15 — BUG-006 retry budget exhausted

- BUG-006 reached five evidence calls and one proposed payment-status hypothesis.
- Direct Gemini and configured fallback retries exhausted before the Auditor node.
- State is paused and resumable: 7 tool calls and 6 model calls remain under the original budget.


## 2026-09-15 - Azure Foundry provider

- Added Azure AI Foundry model-inference REST provider and direct azure selection.
- fallback now selects Azure after retryable Gemini failures when Azure is configured.
- Added unit coverage for provider selection and request contract.
- Current environment has no Azure Foundry endpoint, key, or deployed model variables, so the saved BUG-006 checkpoint cannot yet run with Azure.


## 2026-09-15 - Azure OpenAI deployment discovery

- Foundry AI Services has no deployed model.
- The existing Azure OpenAI resource has gpt-5-mini deployed.
- Extended the provider to use the Azure OpenAI v1 chat endpoint for that deployment.


## 2026-09-15 - Azure GPT-5 request compatibility

- Live Azure connection reached the deployed gpt-5-mini model.
- Azure returned unsupported_parameter for max_tokens.
- Azure OpenAI v1 requests now use max_completion_tokens; model-inference requests keep max_tokens.


## 2026-09-15 - Azure GPT-5 parameter compatibility

- gpt-5-mini also rejects non-default temperature values.
- Azure OpenAI v1 requests omit temperature and use max_completion_tokens.


## 2026-09-15 - Azure transcript compatibility

- The full investigator request reached Azure but rejected the Gemini transcript role model.
- Azure adapter now normalizes that provider-specific role to assistant.
- Persisted state remains unchanged and portable across providers.


## 2026-09-15 - Azure resume approval boundary

- Azure gpt-5-mini passed a minimal structured-output request.
- The automatic approval review blocked the BUG-006 resume because its saved evidence would be sent to Azure.
- The checkpoint remains intact at step 5 and will not rerun reproduction.


## 2026-09-15 - Azure investigator schema enforcement

- Azure completed BUG-006 decisions but three were rejected by the local decision contract.
- Azure OpenAI v1 now receives the existing strict JSON Schema, matching the OpenRouter contract.
- This changes output enforcement only; no target application operation is added.


## 2026-09-15 - BUG-006 Azure Evidence Auditor

- Azure Foundry gpt-5-mini audited the persisted BUG-006 candidate and evidence.
- Verdict: INSUFFICIENT, with no contradictions.
- It accepted reproduction evidence but required payment-handler source, ORM transaction evidence, and correlated runtime logs before supporting the root cause.
- The Auditor did not select tools or modify the target application.


## 2026-09-15 - BUG-006 single investigator versus Auditor

| Metric | Single | Single + Auditor |
| --- | --- | --- |
| Correct root cause | No - provider failure before conclusion | No - Auditor returned INSUFFICIENT |
| Unsupported conclusions | No final claim | 0 accepted unsupported claims |
| Missed contradictory evidence | Not measurable | None reported |
| Additional tool calls | 0 | 0 |
| Model calls | 18 | 19 |
| Tokens | 27,235 recorded investigator tokens | 1,710 input + 1,413 output |
| Latency | 325.1 seconds recorded investigation time | 22.9 seconds Auditor call |
| Auditor correctly rejects weak RCA | N/A | Yes |


## 2026-09-15 - README score update rule

- README now has the observed six-bug scorecard: 3 of 6 root causes, or 50 percent.
- Every test, benchmark, resume, and auditor run must update the README scorecard and this dated log before commit.


## 2026-09-15 - Auditor feedback loop

- Auditor contract now requires unsupported claims, missing evidence, required next evidence, and a reason.
- INSUFFICIENT routes through a deterministic feedback node, then returns tool selection to the Investigator.
- CONTRADICTED reopens investigation; SUPPORTED still produces the root-cause report.
- Audit cycles are persisted and bounded at three.


## 2026-09-15 - Auditor feedback-loop verification

- Score: 14 of 14 LangGraph and provider tests passed.
- Covered INSUFFICIENT to Investigator-selected tool to re-audit to SUPPORTED.
- Covered Azure and OpenRouter provider contracts.


## 2026-09-15 - BUG-003 and BUG-005 Azure approval boundary

- The updated loop is implemented and locally verified, but no live BUG-003 or BUG-005 Azure run occurred.
- Automatic approval review rejected both resumes because Azure egress authorization currently covers only BUG-006.
- Both saved checkpoints remain unchanged and resumable.


## 2026-09-15 - BUG-003 and BUG-005 feedback-loop resumes

- BUG-003 retained seven evidence calls but Azure failed before the Auditor; it remains resumable.
- BUG-005 found a legacy `evaluate_evidence` checkpoint transition that no longer matched the graph node name.
- Added a migration from that transition to `evidence_auditor`; no target-app tool replay occurred.


## 2026-09-15 - Explicit Evidence Auditor module

- Extracted the Evidence Auditor to `traceroot/agents/auditor.py`.
- It exposes only the audit prompt, schema, and evidence-only request builder.
- LangGraph now routes to that module; it retains no tool catalog or transcript access.


## 2026-09-15 - Auditor module verification

- Score: 16 of 16 LangGraph and provider tests passed.
- The dedicated Auditor module has an evidence-only input boundary test.


## 2026-09-15 - BUG-005 legacy null-final resume

- BUG-005 exposed a legacy checkpoint with `final: null`.
- Resume now treats a null final report as no final report; evidence remains unchanged.


## 2026-09-15 - Legacy recovery verification

- Score: 17 of 17 LangGraph and provider tests passed.
- Covered legacy `evaluate_evidence` routing and null-final provider-failure recovery.


## 2026-09-15 - Auditor report boundary correction

- Auditor output now contains only verdict and evidence feedback; it cannot generate a root-cause report.
- LangGraph creates the final structured report deterministically only after an evidence-linked supported hypothesis passes validation.
- Auditor prompt now requires both runtime or reproduction evidence and independent subsystem confirmation for SUPPORTED.


## 2026-09-15 - Auditor report boundary verification

- Score: 17 of 17 LangGraph and provider tests passed.
- Verified Auditor-only evidence output and deterministic validated root-cause reporting.


## 2026-09-15 - Retry invalid checkpoint mode

- Added explicit `resume --retry-invalid` for a finished checkpoint stopped by invalid decisions after a contract update.
- It preserves evidence and cumulative budgets, resets only invalid-decision counters, and returns to the Auditor.


## 2026-09-15 - Retry invalid verification

- Score: 18 of 18 LangGraph and provider tests passed.
- Verified retry-invalid reopens only the eligible invalid-decision checkpoint while retaining tool evidence.


## 2026-09-15 - Azure optional-schema compatibility

- Azure strict JSON Schema rejected optional investigator tool fields in BUG-003.
- Azure now receives non-strict JSON Schema; TraceRoot retains authoritative local schema validation.
- A live BUG-003 compatibility request returned HTTP 200.


## 2026-09-15 - Azure optional-schema verification

- Score: 18 of 18 graph and provider tests passed.
- OpenRouter retains strict schema mode; Azure uses compatible non-strict schema mode with local validation.


## 2026-09-15 - Live feedback-loop evaluation

- BUG-003: one additional read-only tool produced implementation evidence; Auditor returned SUPPORTED and root cause was identified.
- BUG-005: Auditor returned INSUFFICIENT with specific database and pool evidence needs; three invalid Investigator decisions prevented tool selection.
- Score updated to 4 of 6 root causes, or 67 percent.


## 2026-09-16 - Investigator decision validation

- Added explicit TOOL_CALL, AUDIT, and BLOCKED modes with evidence goals and target hypothesis IDs.
- Invalid decisions now receive a machine-readable repair error and only two repair attempts.

## 2026-09-16 - Decision validation verification

- Score: 18 of 18 graph and provider tests passed.
- Covered explicit decision modes and bounded structured repair handling.


## 2026-09-16 - Canonical repository validation

- BUG-005 exposed stale repository paths in model-selected tool arguments.
- Decision validation now rejects any repository argument not identical to the checkpoint task repository before tool dispatch.

## 2026-09-16 - Canonical repository verification

- Score: 11 of 11 focused LangGraph tests passed.
- Verified stale repository arguments are rejected before tool dispatch.


## 2026-09-16 - Fresh BUG-006 feedback-loop attempt

- Fresh BUG-006 reproduction was unavailable in the disposable target session.
- It made one reproduction call and no model or Auditor calls.
- BUG-006 is marked NOT EVALUATED for the Auditor feedback-loop experiment.


## 2026-09-16 - Explicit investigation failure taxonomy

- Graph outcomes now separate reproduction, model-provider, model-decision, tool-execution, and tool-permission failures.
- Supported reports now use ROOT_CAUSE_SUPPORTED.

- Day 11 control-plane hardening: strict investigator decisions and explicit failure taxonomy.
- Added separate investigator/auditor/feedback token and latency measurements. Focused verification: 19 passed.

- BUG-006 re-run: disposable target created, but deterministic Docker setup returned docker_unavailable; WSL reports Docker Desktop integration is disabled. No model or Auditor call was made.

- Began TargetRunner abstraction: DockerRunner remains the default controlled backend; LocalRunner is investigation-only and denies reset. Initial focused tests exposed legacy runner-selection assumptions; compatibility correction is in progress.

- TargetRunner compatibility correction verified: 17 reproduction/execution tests passed. Docker remains default; LocalRunner is opt-in and read-only.

- BUG-006 deterministic Docker reproduction passed the benchmark gate: the selected public regression test observed persisted status pending instead of paid.

- BUG-006 live Investigator sent an empty search scope. Empty scope now means public repository root; this fixes a tool-contract usability defect.

- BUG-006 second live run exposed a contract mismatch: read_file enforced 200 lines while its model schema allowed 1,000,199. Tightened the model schema so overlong reads become MODEL_DECISION_FAILURE before tool dispatch.

- BUG-006 resumed graph reached nine read-only tool steps without rerunning reproduction, then ended MODEL_DECISION_FAILURE after Azure invalid JSON and bounded repair exhaustion; Auditor not reached.

- Added proposal-only Remediation Planner: it accepts only ROOT_CAUSE_SUPPORTED, has no tools or write capability, and requires human approval. Planner boundary tests: 2 passed.
