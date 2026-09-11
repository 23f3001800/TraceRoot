# Day 5 implementation log

## Scope

Introduce LangGraph as the explicit orchestration layer for the existing single,
read-only investigator. Keep the Day 4 `InvestigationState` checkpoint as the
only persisted investigation state. No additional agents, MCP, source changes,
database changes, patching, or GitHub actions are in scope.

## Planned graph

`START -> reproduce -> collect_runtime_evidence -> investigate -> evaluate_evidence`

Evaluation routes by state to `investigate`, `report_limitation`, or
`root_cause_report`. A deterministic budget/recovery gate prevents unbounded
retries. Checkpoints will be written only after meaningful graph transitions.

## Changes

- Started Day 5 work; no code change has been made in this entry.

## Dependency and workspace update

- Pinned `langgraph==1.2.11` in both dependency manifests.
- Added local Day-work scripts and temporary files to `.gitignore`.
- LangGraph will use the existing atomic `state.json`; its in-memory graph state
  is never a second checkpoint.
## Existing-state migration

- Evolved `state.json` from version 1 to version 2 in place.
- Added the Day 5 graph view: incident, reproduction, observation references,
  evidence, tool history, provider errors, current subsystem, status and counters.
- Old checkpoints migrate deterministically on load; evidence remains in the
  original Day 4 steps and hypothesis records.
## Graph contracts

- Added a tool-selection-only investigator decision contract.
- Added a separate evidence evaluation contract with YES, NO and BLOCKED routes.
- Added a bounded `max_model_calls` budget to the existing budget object.
## LangGraph implementation

- Added `traceroot.agents.langgraph` with an explicit `StateGraph`.
- Deterministic nodes: reproduce, runtime collection, budget gate, tool execution,
  provider recovery, limitation reporting and finalization.
- Reasoning nodes: investigate selects one tool; evaluate_evidence independently
  decides YES, NO or BLOCKED.
- Each meaningful graph transition writes the existing atomic checkpoint.
## Integration update

- The operator `investigate` and `resume` commands now execute the LangGraph
  orchestration rather than the legacy ReAct loop.
- Legacy state initialization remains schema-compatible so existing tests and old
  checkpoint migration continue to work.
## Graph state typing correction

- Expanded the LangGraph `TypedDict` to cover every persisted Day 4 field the
  graph reads or updates. The graph therefore receives the same checkpoint state,
  not a reduced copy.
## Graph tests

- Added tests for graph node visibility, state-dependent routes, deterministic
  budget handling, provider recovery/resume and supported-root-cause finalization.
## Graph test corrections applied

- Added the graph routing fields to the persisted schema.
- The investigator now explicitly hands off to evaluation after its post-tool
  hypothesis update, preserving separate investigation and evaluation duties.
## Checkpoint schema fix

- Tool completion now clears `planned_action` to null instead of removing the
  required persisted field, so every transition remains schema-valid.
## Graph state handoff correction

- Successful tools now route back to the investigator for a post-observation
  hypothesis update before evaluation.
- Graph results now summarize the final LangGraph node state rather than the
  pre-invocation Python object.
## Legacy compatibility fix

- Added null graph-routing defaults to legacy Day 4 state initialization so its
  existing tests and checkpoint format remain valid under the version 2 schema.
## Operator guide and comparison

- Added the `--max-model-calls` operator limit for a new graph run; resumed runs
  keep their original persisted limit.
- Added the Day 5 graph guide, node/edge/state/checkpoint definitions and a
  direct comparison against the Day 3/4 ReAct loop.## Verification and live-run attempt

- The graph CLI exposes its model-call budget.
- Full automated validation passed: 97 passed and 4 skipped.
- A fresh disposable BUG-001 session could not be created because Docker
  returned the structured `docker_unavailable` result. No target-app files or
  database data were changed.
## Day 4 checkpoint compatibility

- Older provider-failure checkpoints did not carry a Day 5 recovery marker.
- Graph resume now recognizes their recorded provider failure, clears only the
  provisional failure report, and continues from `investigate` without replaying
  saved reproduction or tool results.
## Live provider authorization boundary

- The environment rejected the Day 5 Gemini resume because it would export
  target-app investigation data to an external provider.
- No workaround was attempted. Local graph tests continue to validate routing,
  checkpointing and recovery; a live Gemini graph run requires fresh explicit
  authorization.
## Compatibility correction

- Corrected a newline encoding mistake in the Day 4 resume compatibility edit.
- The graph module now imports before the full validation rerun.

## Legacy checkpoint correction

- Version-1 checkpoints now receive required graph-routing defaults during migration.
- Provider-failure resume falls back to investigate when no older recovery target exists.

