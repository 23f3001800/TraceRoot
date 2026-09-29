# TraceRoot project assessment

Engineering judgment as of 29 September 2026; not a certification.

| Dimension | Rating | Evidence |
| --- | ---: | --- |
| Agentic AI portfolio | 8/10 | Real Azure EduForge incident, bounded Investigator, independent Evidence Auditor, approved sandbox remediation, baseline 0/3 to 3/3 |
| Production readiness | 4/10 | Staging quality ended succeeded_partial; hosted authenticated UI, durable shared state, remote sandbox, and public recovery verification remain incomplete |
| Overall portfolio | 7/10 | Strong safety architecture and measurable recovery, with operational gaps documented |

The Azure image is in ACR. The private `traceroot-image-staging` Container App runs that image and Azure reports a healthy revision. It has internal ingress only; authenticated public access and an external homepage check remain open.

## Agentic AI engineering concepts covered

- Agent design: three AI decision roles, with tools limited by role.
- Orchestration: LangGraph, CrewAI, and AutoGen adapters over one bounded core.
- Tool contracts and MCP policy: schema constrained, read-only evidence access.
- Durable workflow: checkpoints, pause/resume, event replay, cumulative budgets.
- Observability: logs, metrics, job warnings, token/cost/latency tracking.
- Evidence quality: independent Auditor and citation checks.
- Human oversight: exact patch approval and separate publish/deploy gates.
- Isolation and evaluation: disposable Docker execution, deterministic regression, baseline comparison.
- Deployment: isolated staging with production promotion locked.

Missing for a complete production story: clean end-to-end staging quality, authenticated shared UI, persistent cloud state, remote sandbox jobs, normalized RAG/tool traces, and recovery monitoring. See the [roadmap](limitations-roadmap.md).

These boundaries follow [OWASP's least-privilege agent guidance](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html); future trace normalization can use [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/).
