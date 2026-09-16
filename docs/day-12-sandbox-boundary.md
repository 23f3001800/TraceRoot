# Day 12 - Sandbox Executor and Verifier Boundary

The executor accepts only a human-approved bounded unified diff for the registered disposable Docker session. It rejects LocalRunner, absent approval, other repositories, and invalid patches. Actual patch application remains disabled. The verifier is Docker-only and is reserved to rerun reproduction plus regression after future execution.

Verification: 2 executor-boundary tests passed.

## Approval and patch hardening

Approval records bind approval ID, investigation ID, patch SHA-256, repository, session, approver, timestamps, status, and consumption state. The executor rejects unknown, expired, consumed, foreign-session, and hash-mismatched approvals. Patch policy rejects traversal, protected paths, binary or symlink patches, deletion, oversized patches, too many files, and excessive changed lines. Patch application remains disabled until Docker-side git apply --check is implemented.

Verification: 5 approval and patch-policy tests passed.
