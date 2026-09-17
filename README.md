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
- Patch application is disabled. The executor rejects unsafe or unapproved patches.

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

Approved Docker patch application is implemented and consumes the exact approval. It is unit-tested but not yet exercised with a real human-approved patch.

Deterministic verifier statuses are implemented and tested: FIX_VERIFIED, REPRODUCTION_STILL_FAILS, REGRESSION_INTRODUCED, and VERIFICATION_TOOL_FAILURE.

Sandbox rollback restores the base session image; sandbox destruction removes session-owned containers, network, and images.

- BUG-001 end-to-end remediation is blocked until Docker Desktop WSL integration is available; no patch was applied.

## Approval interface

Run `python -m traceroot approval-ui --session SESSION --patch-file PATCH --investigation-id ID`. Open the displayed localhost URL, inspect the exact diff and SHA-256, then approve it. The UI is loopback-only and writes the same bound approval record used by the executor.
