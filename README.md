# TraceRoot

**Autonomous incident monitoring and recovery for deployed AI applications.**

TraceRoot detects failures from production telemetry, correlates evidence across application and AI components, independently audits the proposed root cause, and prepares bounded remediation. Investigation is read-only; source, runtime, and deployment changes require explicit human approval and deterministic verification.

## What it demonstrates

AI applications fail across application code, models, providers, prompts, retrieval, tools, infrastructure, and data. TraceRoot turns those disconnected signals into one evidence-backed workflow:

1. Monitor deployed health, jobs, metrics, logs, and traces.
2. Detect runtime, application, model, provider, RAG, and tool failures.
3. Open an incident automatically, without a manual bug report.
4. Correlate evidence into testable root-cause hypotheses.
5. Use an independent, tool-less Evidence Auditor to validate cited claims.
6. Propose the smallest bounded remediation.
7. Require exact human approval before any write.
8. Execute only in disposable Docker and verify actual recovery.

## Live Azure integration

TraceRoot is connected read-only to the deployed **EduForge AI** application on Azure App Service. The connector collects health and readiness, job state and warnings, token usage and cost, measured application/model counters, and bounded Prometheus telemetry. It stores credential references rather than credential values, keeps a durable cursor, computes counter deltas, and suppresses duplicate incidents.

### Verified live result — 20 September 2026

A controlled authenticated job exercised the real Azure-backed EduForge pipeline:

| Result | Measured value |
| --- | ---: |
| Job ID | `446c7d47-1e03-41fa-a432-a47aea05557e` |
| Terminal state | `succeeded_partial` |
| Completed stages | 10/10 |
| Model attempts | 16 |
| Tokens consumed | 30,835 |
| Warning | `educational-classification: low confidence: grade_band` |
| HTTP 5xx in retained Azure sample | 0 |

This is a real model-quality degradation, not a fixture: the application completed only partially after reporting low-confidence classification. TraceRoot recognized the transition and warning as correlated application and model evidence, automatically opened incident `b57b4ab4fc21`, and invoked the independent Evidence Auditor once with a 1,024-token output cap, no thinking budget, and no retries.

The Auditor returned **SUPPORTED** with two citations: the application-level `succeeded_partial` observation and the model-level low-confidence classification warning.

The approval-bound remediation was then evaluated entirely in disposable Docker. Low-confidence grade-band resolution improved from **0/3 at baseline**, to **1/3 after the first approved patch**, to **3/3 after the final approved correction**. Deterministic verification returned `FIX_VERIFIED`: all **49 focused classification tests passed**, and the broader unit suite reported **429 passed, 1 skipped, 0 failed**. Production was not changed and no PR was created.

## Architecture

```mermaid
flowchart TD
    A[Deployed AI application]
    B[Read-only monitoring]
    C[Automatic incident]
    D[Investigator and evidence tools]
    E[Independent Evidence Auditor]
    F[Bounded remediation proposal]
    G{Human approval}
    H[Disposable Docker execution]
    I[Deterministic recovery verification]

    A --> B --> C --> D --> E
    E -->|More evidence needed| D
    E -->|Root cause supported| F --> G
    G -->|Approved| H --> I
    G -->|Rejected| C
```

Monitoring extends the existing incident state machine. It does not add another agent or bypass investigation, audit, approval, execution, or verification boundaries.

### Component count

TraceRoot has **three AI decision roles**:

1. **Investigator** — selects bounded read-only evidence actions and maintains hypotheses.
2. **Evidence Auditor** — judges only supplied evidence and has no tools.
3. **Remediation Planner** — proposes a bounded change only after the root cause is supported.

The **Sandbox Executor** and **Verifier** are deterministic software components, not autonomous or model-driven agents. Human approval is a security boundary, not an agent. TraceRoot uses models for constrained judgment and ordinary code for enforcement and verification.

## Safety boundaries

- Investigation tools are read-only and schema constrained.
- Runtime connectors use HTTPS origins, bounded reads, timeouts, and credential references.
- Secrets and authorization fields are redacted before evidence is stored.
- Private reasoning, prompts, and tool arguments are not published.
- The Evidence Auditor has no tools and cannot manufacture evidence.
- Remediation remains proposal-only until exact human approval.
- Approved changes run only in a disposable Docker environment.
- Recovery requires the original reproduction and regression suite to pass.
- Target commits and PR preparation require separately bound approvals.

## Run

Requirements: Python 3.12, Docker for sandbox execution, and one configured model provider.

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q
```

Start autonomous read-only monitoring:

```bash
python3 -m traceroot monitor \
  --name eduforge-ai \
  --url https://eduforge-ai.azurewebsites.net \
  --repository https://github.com/23f3001800/EduForge-AI \
  --workspace-dir .traceroot-workspace \
  --state-file .traceroot-monitor.json \
  --interval 30
```

Add `--job-id JOB_UUID` to watch a deployed job. Other operator entry points:

```bash
python3 -m traceroot prepare --repository TARGET_REPOSITORY --docker "$(command -v docker)"
python3 -m traceroot investigate --session SESSION --task-file task.json --env-file .env
python3 -m traceroot workspace-ui
python3 -m traceroot approval-ui --session SESSION --patch-file PATCH --investigation-id ID
```

## Verification

- Monitor plus workspace/recovery integration: **32 tests passed** before watched-job support.
- Repository regression run: **169 passed, 5 skipped**.
- One environment-only failure remained because `google.genai` was absent from the active interpreter.
- Real Docker remediation previously completed with exact approval, policy validation, passing reproduction and regression, approval consumption, and sandbox destruction.

Test totals are evidence from named runs, not invented status indicators.

## Repository map

| Path | Responsibility |
| --- | --- |
| `traceroot/autonomous_monitor.py` | Telemetry, detection, correlation, deduplication, audit handoff |
| `traceroot/agents/` | Three AI roles plus deterministic approval, execution, and verification components |
| `traceroot/runtime_connectors.py` | Credential-reference gateway and redaction |
| `traceroot/workspace_events.py` | Durable incident/event journal |
| `traceroot/tools/` | Bounded read-only evidence tools |
| `ui/workspace/` | Local incident operations console |
| `tests/` | Contract, recovery, sandbox, provider, workspace, and monitoring tests |
| `docs/` | Architecture decisions, policies, benchmarks, operator guides |

## Known limitations

- The recovery result is sandbox evidence only; deployment to staging or production remains a separate, explicitly approved action.
- Azure logs and distributed traces are not retained because the deployed app has no Log Analytics diagnostic routing.
- RAG and tool signals need first-class normalization when the application exports those spans.
- EduForge metrics currently reset on application restart.
- Recovery should be proven on a dedicated staging deployment before production remediation is enabled.

TraceRoot favors evidence over confident prose, explicit contracts over unrestricted tools, and recoverable execution over direct production mutation. Missing evidence produces `INSUFFICIENT`, not a plausible story.

Licensed under [LICENSE](LICENSE).
