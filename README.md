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
| BUG-003 | PROVIDER_FAILURE | 0/1 | 7 | - | Not run |
| BUG-004 | ROOT_CAUSE_IDENTIFIED | 1/1 | 3 | - | Not run |
| BUG-005 | PROVIDER_FAILURE | 0/1 | 2 | - | Not run |
| BUG-006 | INSUFFICIENT evidence | 0/1 | 5 | 19 | Correctly rejected weak RCA |
| **Total** | **3 of 6 root causes** | **50%** |  |  | **1 of 1 weak RCA rejected** |

BUG-006's Azure Evidence Auditor added no tools, one model call, 3,123 tokens,
and 22.9 seconds. It required payment-handler, persistence, and correlated log
evidence before accepting a root cause.

BUG-003 and BUG-005 feedback-loop runs are pending explicit Azure egress approval; no score was changed.

### Score update rule

Every test, benchmark, resume, or auditor run must update this scorecard and the
corresponding dated entry in `docs/day-7-log.md` before committing. Include status,
root-cause score, tool calls, model calls, tokens when available, latency when
available, and the auditor verdict when one ran.

Latest implementation verification: **16/16 tests passed** on 2026-09-15 for the
Auditor feedback loop, Azure provider, and OpenRouter provider.

