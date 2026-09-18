# TraceRoot

TraceRoot investigates software incidents, records evidence, and produces a root-cause report. It runs against a separate target repository and preserves the target Git history.

## What it does

1. Reproduces the reported failure.
2. Collects bounded runtime evidence.
3. Uses one read-only Investigator to select evidence tools.
4. Uses an independent Evidence Auditor to check root-cause claims.
5. Creates a proposal-only remediation plan only after ROOT_CAUSE_SUPPORTED.

The current agents are Investigator, Evidence Auditor, and Remediation Planner. The planner has no tools or write permissions.

## Architecture

```mermaid
flowchart TD
    I[Incident] --> R[Deterministic reproduction]
    R --> INV[Investigator]
    INV --> TG[Read-only tool gateway]
    TG --> ES[Shared evidence state]
    ES --> AUD[Evidence Auditor]
    AUD -->|Insufficient or contradicted| INV
    AUD -->|Supported| RCA[Root-cause report]
    RCA --> PLAN[Remediation Planner]
    PLAN --> HUMAN[Human approval]
    HUMAN --> GATE[Approval and patch policy]
    GATE --> SANDBOX[Disposable Docker sandbox]
    SANDBOX --> EXEC[Sandbox Executor]
    EXEC --> VERIFY[Deterministic Verifier]
    VERIFY -->|Verified| GIT[Future branch commit draft PR]
    VERIFY -->|Failed| DISCARD[Discard sandbox]
```

## Safety boundaries

- Target source, logs, database inspection, configuration, Git, and tests are read-only during investigation.
- Benchmark ground-truth paths are blocked.
- LocalRunner is investigation-only.
- DockerRunner is required for future execution.
- Exact-diff human approvals bind patch hash, investigation, repository, sandbox session, expiry, and consumption state.
- Patch application is allowed only after exact human approval, deterministic patch-policy validation, Docker-side git apply --check, and Docker-only execution.

## Status

BUG-003 reached ROOT_CAUSE_SUPPORTED with an Auditor verdict of SUPPORTED.

BUG-006 has a deterministic Docker reproduction: the public regression test expected paid and observed pending. Its live graph run later ended as MODEL_DECISION_FAILURE after invalid Azure output, before the Auditor ran.

BUG-005 remains incomplete. Its Auditor identified missing runtime pool, stack-trace, and request-correlation evidence.

## Run

Prepare an isolated target environment:

    python -m traceroot prepare --repository TARGET_REPOSITORY --docker "$(command -v docker)"

Run an investigation using a sanitized target checkout and a local provider configuration:

    python -m traceroot investigate --session SESSION --task-file task.json --env-file .env

See [manual runs](docs/day-6-manual-runs.md) and [state and recovery](docs/investigation-state.md).

## Verification

The verifier must be deterministic because the planner must not judge its own proposal. When enabled, it returns FIX_VERIFIED only if the original reproduction passes and the regression suite passes. Other outcomes distinguish persistent reproduction failure, regressions, and execution failure.

Implementation logs and benchmark results are in [docs](docs/).

Latest application verification: 122 passed, 4 skipped.

Docker patch dry-run verification: 7 executor and dry-run tests passed.

Approved Docker patch application was exercised with a real human-approved BUG-001 patch. The approval was consumed, the original reproduction passed, and the regression suite passed.

Deterministic verifier statuses are implemented and tested: FIX_VERIFIED, REPRODUCTION_STILL_FAILS, REGRESSION_INTRODUCED, and VERIFICATION_TOOL_FAILURE.

Sandbox rollback restores the base session image; sandbox destruction removes session-owned containers, network, and images.

- BUG-001 end-to-end remediation completed: exact approval, Docker patch check, derived-image apply, reproduction 1/1 passing, regression 14/14 passing, and sandbox destruction.

## Approval interface

Run `python -m traceroot approval-ui --session SESSION --patch-file PATCH --investigation-id ID`. Open the displayed localhost URL, inspect the exact diff and SHA-256, then approve it. The UI is loopback-only and writes the same bound approval record used by the executor.

The full local dashboard lives in `ui/` and is served by `approval-ui` on localhost.

Approval UI runtime smoke test added after missing import fix.

The approval dashboard uses a loopback WebSocket for live backend-to-frontend approval events. APIs live under `traceroot/api/`.

Docker patch dry-run now streams the approved diff with interactive stdin.

The UI is an incident-response workspace, not a coding editor; it shows evidence, audit, remediation, and sandbox approval state.

## Latest live remediation result

BUG-001 completed in a disposable Docker session. The exact approved patch was applied to a derived image only. The original reproduction passed **1/1** and the regression suite passed **14/14**. The approval was consumed and the session containers, network, base image, and derived image were destroyed.

Latest benchmark result: BUG-003 exact approved remediation returned FIX_VERIFIED in Docker. The retry reproduction passed 1/1 and the regression suite passed 15/15; its disposable sandbox was destroyed.

Latest benchmark reproduction: BUG-004 failed 1/1 in Docker. Payment returned HTTP 500 where 201 is expected after the httpx upgrade. Its review-only candidate replaces obsolete httpx proxies with proxy and awaits exact approval.

## Repository hygiene

Generated sessions, caches, logs, local credentials, UI caches, and generated run documents are ignored. Required README and milestone documentation remain tracked.

Provider probe: Gemini 2.5 Flash returned MODEL_PROVIDER_FAILURE in 1.98 seconds for a harmless JSON health check. No target or incident data was sent.

Provider probe: OpenRouter nex-agi/nex-n2.5-mini:free returned valid JSON in 1.24 seconds (24 input, 8 output tokens). It is the preferred provider before Azure fallback.

## Verified branch workflow

After FIX_VERIFIED, TraceRoot can create a clean local traceroot/ branch and commit the exact policy-validated patch. It never pushes, merges, or opens a PR. Focused verification: 2 passed.

## Draft PR preparation

After FIX_VERIFIED, TraceRoot can prepare a bounded PR-ready title and body from incident, evidence, remediation, files, verification, and limitations. It rejects secrets and unverified requests, and does not publish. Focused verification: 2 passed.

Latest full verification: 138 passed, 4 skipped.

## Target commit approval

Local target branch commits require a separate persisted approval bound to target repository, sandbox session, exact action hash, branch, patch, commit message, and FIX_VERIFIED status. The approval is consumed after the commit succeeds. Focused verification: 8 passed.

## MCP gateway

TraceRoot now has a read-only MCP gateway for Git, runtime, and database tool families. It preserves structured results, separates transport failure from tool failure, and denies arbitrary tool families. Focused verification: 3 passed.

## Explicit MCP policy

The enforced [MCP permission policy](docs/mcp-permission-policy.md) sets MCP_ACCESS_MODE to read_only. Git, runtime, and database evidence tools are allowed; write verbs are denied. Focused verification: 4 passed.

## Incident workspace and demo

Run `python -m traceroot workspace-ui` to open a loopback-only incident workspace. It saves reports locally without starting agents or changing targets. See [final benchmark](docs/final-benchmark.md) and [local demo](docs/local-demo.md). Workspace verification: 1 passed.

Live workspace verification: loopback incident API responded successfully with an empty local report list.

## Live operator channel

The incident workspace has a loopback WebSocket channel for operator messages and checkpoint requests. It broadcasts events to the dashboard and does not start or alter an inactive investigation. Verification: one local message delivery passed.

## Incident workspace event stream

The incident workspace now uses a three-panel investigation console: stages and agents, a live event stream, and evidence/state. It uses loopback Server-Sent Events for backend-to-browser semantic events and HTTP POST for incident reports, messages, pause, and resume requests. It never exposes private model reasoning.

See [workspace event contract](docs/workspace-event-contract.md) and [local demo](docs/local-demo.md).

Verification: workspace SSE persistence test passed; live loopback API returned an empty incident list and the `workspace.ready` SSE event.

Full regression verification after the SSE workspace update: 143 passed, 4 skipped.
