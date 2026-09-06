# TraceRoot
Multi-Agent Incident Investigation and Recovery for AI Applications


Given a failure in a running software system, TraceRoot autonomously reproduces the problem, investigates across source code, runtime state, logs, databases, tests and deployment history, tests competing hypotheses, identifies an evidence-backed root cause, and performs a bounded remediation only after verification and human approval where required.
## Repositories

TraceRoot lives here. Its standalone commerce target is a sibling repository at
../target-app, with an independent .git directory and the app's extracted commit
history. The original TraceRoot commits remain intact.

See [tool design](docs/tool-design.md) and [input contract](docs/input-contract.md)
for the initial read-only investigation interface. No tools or agents are
implemented yet. Provide a sanitized target checkout to investigations; never
expose evaluator ground truth or the main repository's historical Git objects.
