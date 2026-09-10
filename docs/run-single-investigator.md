# Run and resume a single investigator

From `/home/vikas/TraceRoot` in WSL, configure `GEMINI_API_KEY` in local `.env`.
Gemini 3.6 Flash receives public target evidence through six read-only tools.

1. Prepare a disposable environment:

```bash
.venv/bin/python -m traceroot prepare \
  --repository /home/vikas/target-app \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
```

2. Copy `data.session`, then start:

```bash
SESSION='/home/vikas/TraceRoot/.traceroot-runs/PASTE_SESSION_ID'
.venv/bin/python -m traceroot investigate \
  --session "$SESSION" \
  --task-file docs/investigator-task.example.json \
  --env-file .env \
  --max-tool-calls 15 \
  --max-seconds 900 \
  --model-timeout 90
```

The first progress event prints the run ID. Results live under
`$SESSION/agent-runs/RUN_ID/`. `state.json` holds durable state; `summary.json`
reports `phase`, `resumable`, cumulative counters and stopping reason.
Provider failures appear separately from application observations.

3. If the provider exhausts retries, copy the same run ID and resume:

```bash
RUN_ID='PASTE_RUN_ID'
.venv/bin/python -m traceroot resume \
  --session "$SESSION" \
  --run-id "$RUN_ID" \
  --env-file .env
```

Resume reloads completed observations and hypotheses. It does not repeat a
successful reproduction or reset the original budgets. Keep the disposable
session running until finished. After a process crash, the same resume command
works; an unknown in-flight tool outcome is stopped for operator review.
A completed run returns its saved result without further investigation.

4. Review `final.json`, `summary.json`, and `trajectory.jsonl`. Check evidence
citations and hypothesis transitions before comparing with private ground truth.
Never supply evaluator documents or benchmark files to the model.

5. After investigation is finished, clean up the disposable environment:

```bash
.venv/bin/python -m traceroot cleanup --session "$SESSION"
```

The checkpoint and evidence files remain for review. Cleaned-up sessions cannot
continue collecting live evidence. See [state and recovery](investigation-state.md)
for contracts, failure semantics and cumulative budget rules.
