# Your steps

## 1. Keep Docker Desktop running

Use an Ubuntu/WSL terminal. TraceRoot and target-app remain separate repositories.

```bash
cd /home/vikas/TraceRoot
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

The ordinary suite runs 52 checks; four Docker integration checks skip without a prepared session.

## 2. Prepare a disposable environment

```bash
.venv/bin/python -m traceroot prepare \
  --repository /home/vikas/target-app \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
```

Copy data.session from the JSON result. Substitute that path below.

```bash
SESSION='/home/vikas/TraceRoot/.traceroot-runs/PASTE_SESSION_ID'
```

On native Linux, pass your Docker executable path instead.

## 3. Reproduce before investigating

```bash
.venv/bin/python -m traceroot call --session "$SESSION" run_reproduction \
  --input '{"repository_path":"/home/vikas/target-app","timeout":60}'
```

Check status, reproduced, expected, observed, and exit_code. A successfully observed failure has status=ok.

## 4. Read the correlated logs

Copy the request_id from reproduction stdout and metadata.run_id from its result.

```bash
.venv/bin/python -m traceroot call --session "$SESSION" read_logs \
  --input '{"source":"application","request_id":"PASTE_REQUEST_ID","run_id":"PASTE_RUN_ID","limit":5}'
```

Distinguish application errors from collector_errors. Record which hypotheses the evidence supports or weakens.

## 5. Choose the next tool from evidence

Use names learned from logs or search results. Replace these placeholder values; do not guess affected files beforehand.

```bash
.venv/bin/python -m traceroot call --session "$SESSION" search_code \
  --input '{"repository":"/home/vikas/target-app","query":"PASTE_OBSERVED_SYMBOL","path_scope":"app","result_limit":10}'

.venv/bin/python -m traceroot call --session "$SESSION" read_file \
  --input '{"repository":"/home/vikas/target-app","file_path":"PASTE_DISCOVERED_FILE","start_line":1,"end_line":40}'

.venv/bin/python -m traceroot call --session "$SESSION" inspect_database \
  --input '{"operation":"list_constraints","table":"PASTE_OBSERVED_TABLE","limit":20}'

.venv/bin/python -m traceroot call --session "$SESSION" run_tests \
  --input '{"repository":"/home/vikas/target-app","test_selector":"PASTE_DISCOVERED_TEST","timeout":60}'
```

For the full suite, omit test_selector. For a filtered suite, supply marker="not regression".

## 6. Verify tool permissions

```bash
TRACEROOT_TEST_SESSION="$SESSION" .venv/bin/python -m pytest -q
```

Expected: 56 passing TraceRoot tests. The target application's intentional failure is observed separately through run_tests.

## 7. Review the trace, then clean up

Read manual-investigation-bug-001.md after your own investigation. It contains the answer and must remain hidden during future evaluations.

```bash
.venv/bin/python -m traceroot cleanup --session "$SESSION"
```

Cleanup removes session containers and network; database tmpfs disappears. Private evidence and the reusable image remain locally.

Your responsibility: start Docker, run these commands, and review the evidence. Implementation, isolation checks, and the recorded investigation are complete.

Session files contain disposable credentials; keep .traceroot-runs private.
