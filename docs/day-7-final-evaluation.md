# Day 7 Final Evaluation

## Best result per benchmark

| Benchmark | Status | Calls | Evidence-backed finding |
|---|---:|---:|---|
| BUG-001 | ROOT_CAUSE_IDENTIFIED | 4 | Bulk discount total violates the database order-total constraint. |
| BUG-002 | ROOT_CAUSE_IDENTIFIED | 5 | Deployment payment region differs from the supported region. |
| BUG-003 | PROVIDER_FAILURE | 7 | Retry path creates a duplicate order because it does not reuse the idempotency key. |
| BUG-004 | ROOT_CAUSE_IDENTIFIED | 3 | Updated httpx rejects the obsolete `proxies` client argument. |
| BUG-005 | PROVIDER_FAILURE | 2 | QueuePool exhaustion produces order-request timeouts. |
| BUG-006 | PROVIDER_FAILURE | 2 | Reproduction and runtime logs are saved; a root cause was not established. |

## Observed gaps

- Provider failures interrupted BUG-003, BUG-005, and BUG-006 after checkpoints were safely saved.
- Models occasionally violate structured decision contracts despite valid evidence.
- BUG-006 needs a successful model call after runtime evidence collection.

## Specialist added next: Evidence Auditor

The Evidence Auditor receives only the final candidate, cited evidence IDs, and the hypothesis registry. It independently returns `ACCEPT`, `REJECT`, or `NEEDS_EVIDENCE`.

It cannot select tools, modify code, access the database, or replace the investigator. Its purpose is to prevent unsupported conclusions once provider reliability is restored.

Do not add domain-specific code, database, or fix agents yet. Current failures primarily involve provider availability and decision-contract compliance, not missing investigation capability.
