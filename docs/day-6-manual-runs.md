# Manual Day 6 runs

Run in Ubuntu/WSL Bash from `/home/vikas/TraceRoot`. Docker must be working;
keep GEMINI_API_KEY in local `.env`. Current model: `gemini-3.6-flash`.

## 1. Create one isolated variant

```bash
cd /home/vikas/TraceRoot
export BUG=bug-003
export CASE_DIR=$(mktemp -d /tmp/traceroot-manual-XXXXXX)
git clone https://github.com/23f3001800/target-commerce-api.git "$CASE_DIR/repo"
git -C "$CASE_DIR/repo" checkout stable-v1
git -C "$CASE_DIR/repo" apply --ignore-space-change "$PWD/benchmarks/$BUG/introduced.patch"
.venv/bin/python -m traceroot prepare --repository "$CASE_DIR/repo" --docker "$(command -v docker)"
```

Stop if setup fails. Copy the returned session path as SESSION below.
Repeat in a fresh CASE_DIR for every case; never stack patches.

## 2. Create task.json and investigate

Save task.json in CASE_DIR, replacing REPOSITORY with the printed value of
`echo "$CASE_DIR/repo"` and REPORT with the exact report below:

```json
{"repository":"REPOSITORY","bug_report":"REPORT","reproduction_command":null,"constraints":["read-only investigation","benchmark folder forbidden","no code changes","no database changes"]}
```

| BUG | REPORT |
|---|---|
| bug-003 | Some users see duplicate orders after retrying a request. |
| bug-004 | Payment processing started failing after a dependency update. |
| bug-005 | The API works initially, but after several requests, order requests become slow or fail. |
| bug-006 | Orders are successfully created, but some successful payments leave the order status as PENDING. |

```bash
.venv/bin/python -m traceroot investigate --session SESSION --task-file "$CASE_DIR/task.json" --env-file .env --max-tool-calls 12 --max-model-calls 20 --max-seconds 600 --model-timeout 90
```

A nonzero exit can mean a recorded non-success outcome; read the result.

## 3. Resume, score, clean up

Artifacts: `SESSION/agent-runs/RUN_ID/` contains state.json, summary.json,
final.json and trajectory.jsonl. For a paused run, retain the containers:

```bash
.venv/bin/python -m traceroot resume --session SESSION --run-id RUN_ID --env-file .env
```

Never delete locks or start a competing investigator. Avoid the old
`.day6-live/run_bug.py`: its automatic cleanup can prevent paused-run recovery.

After completion, compare ground truth yourself, never by sending it to Gemini.
Append the trajectory and score to `docs/day-6-log.md`:

| Bug | Run ID | Status | Correct cause? | Tool/model calls | Premature? | Missing evidence |
|---|---|---|---|---|---|---|
| BUG-003 | | | | | | |

Include tool arguments/results, hypothesis summaries, evidence citations,
provider failures and stopping reason. Preserve unsuccessful runs too.
Do not store hidden chain-of-thought. When finished:

```bash
.venv/bin/python -m traceroot cleanup --session SESSION
```

## Current gaps and agent decisions

| Observed gap | Improve first |
|---|---|
| Docker/provider interruptions | Deterministic setup, recovery and diagnostics. |
| State-assertion failures previously stopped investigation | Validate whether failed tests actually reproduce the incident. |
| BUG-002 lacks direct deployment evidence | Bounded, sanitized runtime/configuration access. |
| Source tools exclude Git history/deployment files | Tool coverage for dependency/configuration investigations. |
| BUG-001/002 had invalid model decisions | Clearer contracts and validation feedback. |

BUG-001/002 found the intended mechanisms. That alone does not justify more
agents. Complete BUG-003–006 first, then use repeated failures to choose:

- Code/Dependency investigator: version/API compatibility confusion.
- Runtime investigator: timing/resource-evidence mistakes.
- Data/DB investigator: persisted-state or transaction reasoning mistakes.
- Evidence Critic: unsupported root-cause conclusions.

Compare against the single investigator with the same budgets. More agents
cannot repair missing tools or Docker/provider availability.
