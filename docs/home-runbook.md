# TraceRoot home runbook

TraceRoot's operator application opens at the server root, not at a dashboard
subpath:

```text
http://127.0.0.1:8875/
```

## Start locally

From the repository root:

```bash
python3 -m pip install -e '.[orchestrators]'
python3 -m traceroot workspace-ui \
  --workspace-dir .traceroot-workspace \
  --host 127.0.0.1 \
  --port 8875
```

Open `http://127.0.0.1:8875/`. Do not append `/dashboard`; that route does not
exist. The home page contains incident intake, live agent steps, evidence,
hypotheses, runtime/tool views, cost and latency, approvals, sandbox execution,
and verification results.

## Run monitoring alongside the home page

Start the hardened monitor separately:

```bash
docker compose -f deploy/monitor/compose.yaml up --build -d monitor
```

Both processes must use the same workspace directory if the home page should
display incidents created by the monitor. The provided monitor stores its data
inside the Compose volume; for a host-served home page, run the monitor CLI with
`--workspace-dir .traceroot-workspace`, or explicitly export/copy the bounded
public incident journal from the volume. Do not mount the Docker socket into the
monitor container.

## Network deployment

`--host 0.0.0.0` permits access through the host network. Put an authenticated
TLS reverse proxy in front of it and restrict the source network. TraceRoot's
workspace API intentionally accepts only localhost host/origin values by
default, so exposing it to another hostname requires a separately reviewed
trusted-origin configuration; do not weaken that check ad hoc.

## Verification

```bash
curl --fail http://127.0.0.1:8875/
curl --fail http://127.0.0.1:8875/api/capabilities
python3 -m pytest -q
```

Stop the home-page process with `Ctrl+C`. Stop the monitor with:

```bash
docker compose -f deploy/monitor/compose.yaml down
```
