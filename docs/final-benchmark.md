# Final Benchmark Snapshot

This snapshot records completed evidence, not projections.

| Benchmark | Reproduction | Auditor / RCA | Remediation | Verification |
| --- | --- | --- | --- | --- |
| BUG-001 | Reproduced before remediation | Evidence-backed | Exact approved Docker patch | FIX_VERIFIED: 1/1 reproduction, 14/14 regression |
| BUG-003 | Reproduced: duplicate IDs 1 then 2 | Previously supported | Exact approved Docker patch | FIX_VERIFIED: 1/1 reproduction, 15/15 regression |
| BUG-004 | Reproduced: payment 500 instead of 201 | Candidate only | Not approved or applied | Pending |
| BUG-005 | Incomplete evidence | Auditor requested runtime pool evidence | Not planned | Pending |
| BUG-006 | Reproduced deterministically | Model decision failure before audit | Not planned | Pending |

## Limits

Two benchmark remediations were proven end-to-end in disposable Docker sessions. This does not establish success for all benchmark categories or historical OSS repositories. Provider failures remain separate from application and tool failures.

## Evaluation notes

- BUG-001 and BUG-003 approvals were bound to exact patches, target sessions, repositories, expiry, and consumption.
- Both verified sandboxes were destroyed after testing.
- OpenRouter free-model health probe succeeded. Gemini health probe failed before any investigation work.
