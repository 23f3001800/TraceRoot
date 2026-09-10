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
