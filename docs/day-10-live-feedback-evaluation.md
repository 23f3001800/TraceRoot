# Day 10 - Live Auditor feedback evaluation

| Benchmark | Initial Auditor verdict | Missing evidence requested | Additional tool calls | Audit cycles | Final verdict | Root cause correct | Extra tokens | Extra latency |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |
| BUG-003 | SUPPORTED | None | 1 | 1 | SUPPORTED | Yes | 28,932 | Not isolated |
| BUG-005 | INSUFFICIENT | DB pool state, pool metrics, stack trace, request correlation | 0 | 1 | TOOL_FAILURE | No | 42,492 | Not isolated |
| BUG-006 | INSUFFICIENT | Handler source, ORM persistence, correlated logs | 0 | 1 | INSUFFICIENT | No | 3,123 | 22.9s |

BUG-003 reached support after the Investigator read the order-creation implementation. BUG-005 proves the Auditor returns useful evidence requirements, but Azure emitted three invalid Investigator decisions before it selected a tool. BUG-006 was audited under the earlier terminal checkpoint and did not enter the feedback loop.

The Auditor reduces acceptance of unsupported diagnoses. This does not yet prove improved root-cause accuracy across incomplete cases.
