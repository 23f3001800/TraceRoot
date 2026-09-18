# Local Demo

Start the incident workspace:

```bash
PYTHONPATH=$PWD .venv/bin/python -m traceroot workspace-ui
```

Open http://127.0.0.1:8875. The workspace is loopback-only. If that port is already in use, open the existing page or start with --port 8877.

1. Enter a target repository path.
2. Describe the incident.
3. Optionally add a public reproduction command.
4. Save the report.
5. Follow the semantic events in the center timeline.
6. Send a concise message, pause, or resume request when a run is active.

The dashboard uses Server-Sent Events from `/api/events` for server-to-browser updates and normal POST endpoints for user actions. It records concise event facts, not model chain-of-thought. Reporting and operator messages do not themselves start agents, run commands, access a provider, or modify a target.

The event vocabulary is in [workspace-event-contract.md](workspace-event-contract.md).

For remediation approval, use the separate approval interface:

```bash
PYTHONPATH=$PWD .venv/bin/python -m traceroot approval-ui --session SESSION --patch-file PATCH --investigation-id INCIDENT
```

The approval interface remains separate from the incident workspace.

To display progress from a CLI investigation in the workspace, use the same local workspace directory:

```bash
PYTHONPATH=$PWD .venv/bin/python -m traceroot investigate \
  --session SESSION --task-file task.json --workspace-dir .traceroot-workspace
```

This publishes only bounded graph transitions, tool status, and provider failures. It does not make the workspace responsible for launching an investigation.
