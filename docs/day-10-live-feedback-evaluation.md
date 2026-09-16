# Day 10 - Live Auditor feedback evaluation

| Benchmark | Initial Auditor verdict | Missing evidence requested | Additional tool calls | Audit cycles | Final verdict | Root cause correct | Extra tokens | Extra latency |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |
| BUG-003 | SUPPORTED | None | 1 | 1 | SUPPORTED | Yes | 28,932 | Not isolated |
| BUG-005 | INSUFFICIENT | DB pool state, pool metrics, stack trace, request correlation | 0 | 1 | TOOL_FAILURE | No | 42,492 | Not isolated |
| BUG-006 | NOT EVALUATED | Fresh reproduction unavailable | 0 | 0 | REPRODUCTION_FAILED | N/A | 0 | 0.17s |

BUG-003 reached support after the Investigator read the order-creation implementation. BUG-005 proves the Auditor returns useful evidence requirements, but stale checkpoint paths and earlier invalid decisions prevented a completed second cycle. A fresh BUG-006 reproduction was unavailable before any model or Auditor call, so it is not evaluated for this experiment.

The Auditor reduces acceptance of unsupported diagnoses. This does not yet prove improved root-cause accuracy across incomplete cases.

## 2026-09-16 control-plane re-run

- BUG-006 disposable target setup was attempted. The WSL execution environment reports Docker unavailable and directs the operator to enable Docker Desktop WSL integration. TraceRoot stopped at deterministic setup; no model, Investigator, or Auditor call ran.
- Result: REPRODUCTION_UNAVAILABLE pending Docker Desktop WSL integration. This does not satisfy the BUG-006 gate.
