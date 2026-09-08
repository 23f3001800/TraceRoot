# Run the fourth investigator trial

This command runs one Gemini 3.6 Flash investigator with only six read-only tools.
It creates a fresh filtered snapshot, disposable FastAPI/PostgreSQL environment,
and an auditable trajectory. It does not modify target-app.

From /home/vikas/TraceRoot:

```bash
.venv/bin/python -m traceroot prepare \
  --repository /home/vikas/target-app \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
```

Copy data.session from the result:

```bash
SESSION='/home/vikas/TraceRoot/.traceroot-runs/PASTE_SESSION_ID'

.venv/bin/python -m traceroot investigate \
  --session "$SESSION" \
  --task-file docs/investigator-task.example.json \
  --env-file .env \
  --max-tool-calls 15 \
  --max-seconds 300 \
  --model-timeout 60
```

The investigator returns a structured final object and stores:

```text
$SESSION/agent-runs/RUN_ID/
  initial.json
  trajectory.jsonl
  final.json
  summary.json
```

Score the run against the private ground truth only after it ends. Review tool
selection, result status, evidence pointers, output status, call count, and stop
reason. Do not give benchmark files or this evaluator-only trial report to the
investigator.

Cleanup removes only the named disposable containers and network:

```bash
.venv/bin/python -m traceroot cleanup --session "$SESSION"
```

Gemini retries once only for 429 or transient 5xx responses, with a 0.5-second
delay. The run still stops at the same overall model and investigation deadlines.
