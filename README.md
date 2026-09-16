# TraceRoot
Multi-Agent Incident Investigation and Recovery for AI Applications


Given a failure in a running software system, TraceRoot autonomously reproduces the problem, investigates across source code, runtime state, logs, databases, tests and deployment history, tests competing hypotheses, identifies an evidence-backed root cause, and performs a bounded remediation only after verification and human approval where required.
## Repositories

TraceRoot lives here. Its standalone commerce target is a sibling repository at
../target-app, with an independent .git directory and the app's extracted commit
history. The original TraceRoot commits remain intact.

See [tool design](docs/tool-design.md) and [input contract](docs/input-contract.md)
for the initial read-only investigation interface. Six structured investigation tools are implemented. One Gemini investigator now tracks evidence-linked hypotheses and resumes from durable checkpoints. Remediation is not implemented. Provide a sanitized target checkout to investigations; never
expose evaluator ground truth or the main repository's historical Git objects.

## Tool layer

Start with [your next steps](docs/your-next-steps.md) and [tool contracts](docs/tool-api.md).

The [manual investigation](docs/manual-investigation-bug-001.md) records actual calls and evidence. Keep it hidden during future evaluations.

TraceRoot runs untrusted target tests inside disposable containers. Source access and PostgreSQL inspection are read-only.

## Persistent investigation

Follow [run and resume](docs/run-single-investigator.md) for the operator commands.
See [state and recovery](docs/investigation-state.md) for checkpoint contracts,
cumulative budgets, hypothesis tracking and provider-failure handling.



###  Architecture

                         USER / INCIDENT
                               │
                               ▼
                    ┌────────────────────┐
                    │ Incident Controller │
                    │   deterministic     │
                    └─────────┬──────────┘
                              │
                              ▼
                        Reproduction
                        deterministic
                              │
                              ▼
                     Runtime Observation
                       logs / traces
                              │
                              ▼
                    ┌─────────────────┐
                    │ Triage Agent    │
                    │                 │
                    │ What subsystem? │
                    │ What evidence?  │
                    └────────┬────────┘
                             │
                ┌────────────┼─────────────┐
                ▼            ▼             ▼
        Code Investigator Runtime      Data/DB
            Agent        Investigator Investigator
                │            │             │
          Git / files    logs/traces     schema/SQL
          tests/code     processes/API    persisted state
                │            │             │
                └────────────┼─────────────┘
                             ▼
                    Shared Evidence State
                             │
                             ▼
                    ┌───────────────────┐
                    │ Evidence Critic   │
                    │                   │
                    │ Is root cause     │
                    │ actually proven?  │
                    └─────────┬─────────┘
                              │
                   ┌──────────┴──────────┐
                   │                     │
             insufficient             supported
                   │                     │
                   ▼                     ▼
             investigate again      Root Cause Report
                                         │
                                         ▼
                                 Remediation Planner
                                         │
                                         ▼
                                  Human Approval
                                         │
                                         ▼
                                   Action Executor
                                         │
                                         ▼
                                      Verifier
                                   /           \
                                FAIL           PASS
                                 │               │
                              rollback         resolved

## Evaluation scorecard

Update this section after every test or live benchmark run, before its commit. Record
observed scores only; never replace a failed or incomplete run with an estimate.

| Benchmark | Latest result | Root-cause score | Tool calls | Model calls | Auditor result |
| --- | --- | ---: | ---: | ---: | --- |
| BUG-001 | ROOT_CAUSE_IDENTIFIED | 1/1 | 4 | - | Not run |
| BUG-002 | ROOT_CAUSE_IDENTIFIED | 1/1 | 5 | - | Not run |
| BUG-003 | ROOT_CAUSE_IDENTIFIED | 1/1 | 8 | 13 | SUPPORTED |
| BUG-004 | ROOT_CAUSE_IDENTIFIED | 1/1 | 3 | - | Not run |
| BUG-005 | INCOMPLETE | 0/1 | 3 | 14 | INSUFFICIENT |
| BUG-006 | NOT EVALUATED | N/A | 1 | 0 | Not run |
| **Coverage** | **4 of 5 evaluated root causes** | **80%** |  |  | **1 of 1 weak RCA rejected** |

BUG-006's Azure Evidence Auditor added no tools, one model call, 3,123 tokens,
and 22.9 seconds. It required payment-handler, persistence, and correlated log
evidence before accepting a root cause.

BUG-003 completed with Auditor support. BUG-005 reached Auditor feedback but stopped on invalid Investigator decisions; its score remains unchanged. See `docs/day-10-live-feedback-evaluation.md`.

### Score update rule

Every test, benchmark, resume, or auditor run must update this scorecard and the
corresponding dated entry in `docs/day-7-log.md` before committing. Include status,
root-cause score, tool calls, model calls, tokens when available, latency when
available, and the auditor verdict when one ran.

Latest implementation verification: **18/18 tests passed** on 2026-09-15 for the
Auditor feedback loop, Azure provider, and OpenRouter provider.
Latest score update: **18/18** after explicit Investigator decision validation and bounded repair.
Focused validation: **11/11 LangGraph tests passed** after canonical repository validation.


### Latest control-plane verification

- Strict Investigator decisions: TOOL_CALL, FINAL, or BLOCKED; two invalid attempts end as MODEL_DECISION_FAILURE.
- Explicit result taxonomy separates reproduction, provider, decision, execution, permission, evidence, contradiction, and supported RCA.
- Separate investigator, auditor, and feedback-investigator token and latency measurements.
- Focused LangGraph/provider tests: **19 passed**.

- 2026-09-16 BUG-006 re-run: setup stopped as REPRODUCTION_UNAVAILABLE because Docker Desktop WSL integration is disabled; no agent calls were made.

### Target execution boundary

Investigation can use an explicitly configured LocalRunner when Docker is unavailable. DockerRunner remains default. Any future remediation must require DockerRunner; LocalRunner denies reset and is never an execution backend. TargetRunner exposes run_reproduction, run_tests, get_logs, and reset_target.
- TargetRunner reproduction regression tests: **17 passed**.

- BUG-006 deterministic Docker reproduction: **reproduced** (public test expected paid, observed pending; 1 failed, 0 errors).

- Code search accepts an empty scope as the approved public repository root. Regression test added.

- Read-file schema now matches its 200-line enforcement limit; invalid ranges are rejected before tool dispatch.

- BUG-006 live graph run reached nine tools without rerunning reproduction, then ended MODEL_DECISION_FAILURE after Azure invalid JSON; Auditor was not reached.
