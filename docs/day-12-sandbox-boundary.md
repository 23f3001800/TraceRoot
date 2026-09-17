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

## BUG-001 execution attempt

A disposable BUG-001 checkout was created, but Docker preparation returned docker_unavailable. WSL reports that Docker Desktop integration is disabled. No patch, approval record, model call, or target write occurred.

## Local approval interface

The operator can serve a loopback-only exact-patch approval page through `approval-ui`. It shows patch text, hash, repository, sandbox session, and investigation ID before writing a one-hour approval record.

Verification: 6 approval UI and executor tests passed.

## Full approval dashboard

The root `ui/` directory contains an accessible responsive approval dashboard. The loopback server exposes the patch context through a local API and records approval only after the review form submission.

Verification: 1 focused UI server test passed.

## API and WebSocket communication

Approval APIs live in `traceroot/api/approval.py`. The UI loads patch context from the local API and opens a loopback WebSocket for live context and approval events. HTTP approval submission remains the fallback.

Verification: 2 focused UI API tests passed.

BUG-001 validation found and fixed Docker patch stdin transport. The regenerated candidate passes Docker git apply --check.

The dashboard now presents incident, evidence, audit, remediation, and sandbox state rather than a code-editor workflow. Exact patch byte hashing is verified.

## BUG-001 verified end-to-end remediation

A human approved exact patch c80f421c...e8775 for disposable session c3c42b6d7e6c. TraceRoot validated approval scope and policy, completed Docker-side git apply --check, applied the patch only to a derived sandbox image, then consumed the approval. Deterministic verification returned FIX_VERIFIED: public bulk-order reproduction passed 1/1 and target regression passed 14/14. Sandbox destruction removed that session's containers, network, base image, and derived image. The target checkout still contains its intentionally injected BUG-001 change; the executor did not alter it.

Verification: live Docker reproduction 1 passed; live Docker regression 14 passed.

## BUG-003 Docker reproduction

Disposable Docker session d29d56e32eda ran public test tests/test_bug_003.py. It failed 1/1: repeated retry requests returned different order IDs, 1 then 2. This is runtime evidence only. A review-only candidate now returns an existing order for a repeated idempotency key; it has not been approved or applied.

Verification: live Docker reproduction 0 passed, 1 failed.

## BUG-003 verified end-to-end remediation

A human approved exact patch a97eaae2...73abf for disposable session cddd103aef8a. The derived Docker image reused an existing order for repeated idempotency keys. Deterministic verification returned FIX_VERIFIED: retry reproduction passed 1/1 and target regression passed 15/15. The approval was consumed and the sandbox was destroyed. The disposable checkout retains only its intentionally injected benchmark files; no executor patch was written to it.

Verification: live Docker reproduction 1 passed; live Docker regression 15 passed.

## BUG-004 preparation status

Disposable session be2c2ba7eef1 was inactive before its public reproduction could execute. TraceRoot returned environment_unavailable and stopped. No investigator call, remediation proposal, approval, or patch application occurred.

Verification: reproduction unavailable; no tests executed.

## BUG-004 Docker reproduction retry

A transient inactive-session setup was retried using disposable session 25bebaec18d5. Public test tests/test_bug_004.py failed 1/1: payment returned HTTP 500 where 201 is expected. No remediation proposal, approval, or patch application occurred.

Verification: live Docker reproduction 0 passed, 1 failed.

## BUG-004 remediation candidate

The review-only candidate preserves the configured proxy while replacing the obsolete httpx proxies keyword with proxy. It is bound to disposable session 25bebaec18d5 and awaits exact human approval.

## Repository hygiene

Git ignores generated sessions, logs, coverage, caches, packages, local credentials, UI cache files, and generated run documents. Required README and milestone logs remain versioned.

## Gemini provider health probe

Gemini 2.5 Flash received one harmless structured JSON request with no repository, incident, benchmark, or target data. It returned a non-retryable MODEL_PROVIDER_FAILURE after 1.98 seconds. This is provider availability evidence, not an investigation result.

## OpenRouter provider health probe

Configured free model nex-agi/nex-n2.5-mini:free received the same harmless structured JSON request. It returned valid JSON in 1.24 seconds using 24 input and 8 output tokens. TraceRoot will prefer it before Azure fallback.

## Verified branch and commit workflow

A bounded local Git workflow now requires FIX_VERIFIED, a clean repository, an exact policy-valid patch, a traceroot/ branch name, and a three-to-seven-word commit message. It creates no remote state and never pushes or opens a PR.

Verification: 2 focused isolated Git tests passed.

## Draft PR preparation

TraceRoot now produces a non-publishing PR-ready report only after FIX_VERIFIED. It includes incident, root cause, evidence, remediation, changed files, verification, limitations, branch, commit, and investigation ID. Secrets and unverified requests are rejected.

Verification: 2 focused draft-PR tests passed.

Full verification after draft-PR preparation: 138 passed, 4 skipped.
