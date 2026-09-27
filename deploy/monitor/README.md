# Persistent read-only monitor

This Compose service continuously samples the configured deployed application
and persists its deduplication cursor in a named volume. It runs as an
unprivileged user, has a read-only root filesystem, and does not mount the
Docker socket.

From the TraceRoot repository root:

```bash
docker compose -f deploy/monitor/compose.yaml up --build -d
docker compose -f deploy/monitor/compose.yaml logs -f monitor
docker compose -f deploy/monitor/compose.yaml down
```

Override the target with `TRACEROOT_MONITOR_NAME`,
`TRACEROOT_MONITOR_URL`, `TRACEROOT_MONITOR_REPOSITORY`, and
`TRACEROOT_MONITOR_INTERVAL`. Set `TRACEROOT_ENV_FILE` if provider
credentials are not in the repository `.env`. To watch a particular deployed
job, append `--job-id JOB_UUID` to the service command or run the CLI directly.

`restart: unless-stopped` restarts the process after a crash or Docker restart.
Docker itself remains host-managed: enable Docker Desktop login startup or the
Docker system service if monitoring must resume after a machine reboot.

The monitor is read-only. Investigation may prepare a proposed remediation, but
commit, push, deployment, and production writes retain separate approval gates.
