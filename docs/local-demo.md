# Local Demo

Start the incident workspace:

```bash
PYTHONPATH=$PWD .venv/bin/python -m traceroot workspace-ui
```

Open http://127.0.0.1:8875.

1. Enter a target repository path.
2. Describe the incident.
3. Optionally add a public reproduction command.
4. Save the report.

Reports are stored only in the selected local workspace directory. Saving a report does not start an agent, run a command, access a provider, or modify a target.

For remediation approval, use the separate approval interface:

```bash
PYTHONPATH=$PWD .venv/bin/python -m traceroot approval-ui --session SESSION --patch-file PATCH --investigation-id INCIDENT
```

The workspace and approval interface are loopback-only.
