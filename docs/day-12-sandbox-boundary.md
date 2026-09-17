# Day 12 - Sandbox Executor and Verifier Boundary

The executor accepts only a human-approved bounded unified diff for the registered disposable Docker session. It rejects LocalRunner, absent approval, other repositories, and invalid patches. Actual patch application remains disabled. The verifier is Docker-only and is reserved to rerun reproduction plus regression after future execution.

Verification: 2 executor-boundary tests passed.

## Approval and patch hardening

Approval records bind approval ID, investigation ID, patch SHA-256, repository, session, approver, timestamps, status, and consumption state. The executor rejects unknown, expired, consumed, foreign-session, and hash-mismatched approvals. Patch policy rejects traversal, protected paths, binary or symlink patches, deletion, oversized patches, too many files, and excessive changed lines. Patch application remains disabled until Docker-side git apply --check is implemented.

Verification: 5 approval and patch-policy tests passed.

## Docker patch dry-run

The executor now runs git apply --check inside a Docker sandbox after exact approval and policy validation. The runtime image includes Git. A rejected dry run returns PATCH_REJECTED; patch application remains disabled until the next ordered step.

Verification: 7 executor and dry-run tests passed.

## Approved patch application

The executor creates a disposable Docker container from the session image, applies the exact approved patch through git apply, commits only that container to a derived sandbox image, removes the container, and consumes the approval. It does not touch the original repository. This boundary has focused tests but has not yet been exercised with a real human-approved benchmark patch.

Verification: 8 executor tests passed.

## Deterministic verification

Verification first reruns the original reproduction. If it still fails, status is REPRODUCTION_STILL_FAILS. Otherwise it runs the regression selection. A clean result is FIX_VERIFIED; a failing regression is REGRESSION_INTRODUCED; abnormal tool results are VERIFICATION_TOOL_FAILURE.

Verification: 7 focused executor/verifier tests passed.

## Rollback and destruction

Rollback removes only the derived session patch image and restores the base session image. Destruction calls the existing labeled container/network cleanup and removes session-owned images. The original repository remains unchanged.

Verification: 7 lifecycle, executor, and verifier tests passed.
