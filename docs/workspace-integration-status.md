# Workspace integration status

## Implemented and tested

- Separate incident save/start HTTP actions; subprocess workers run the existing LangGraph graph.
- Durable process identity; operator messages; safe-boundary pause/resume; stop.
- Ordered incident-scoped SSE events and Last-Event-ID replay. The standalone approval
  page also uses HTTP/SSE, not a separate WebSocket port.
- Browser-tested history, filtered evidence selection, replay, snapshots, patch rejection,
  pricing settings and responsive layout.
- Compact agent/tool steps with expandable details, measured token usage and model latency.
  Cost is unavailable until explicit per-model USD rates are configured in Settings.
- Source-only low-risk patch proposals; exact SHA-bound human approval; isolated Docker execution.
- Deterministic reproduction, focused-test and regression verification. Empty or erroneous
  test runs cannot be FIX_VERIFIED.

## Live evidence

Incident `30e7e255af59` used Azure `gpt-5-mini` with `/home/vikas/target-app`
in Docker session `14d19030bfbb`. Run `9f1bcda46559422cb7e6026821b34f2c`
reproduced HTTP 500, accepted steering, paused, and resumed without rerunning reproduction.
Four real Docker database/isolation/timeout tests passed.

This run ended MODEL_DECISION_FAILURE, not a supported root cause.
The graph prompt requested a different decision envelope from its validator.
A graph-specific prompt now matches the schema; citation validation remains strict.

## Remaining phases — not claimed complete

- Phase 4: live supported RCA, concrete patch review/approval, application and verification.
- Phase 5: separately approved publication destination, branch, push and draft PR.
  The workspace publish button is explicitly disabled.
- Phase 6: scoped deployed-runtime and AI/RAG/MCP evidence connectors.
  Azure model inference is working, but is not a runtime evidence connector.
- Phase 7: full acceptance matrix including GitHub-source, deployed targets and publication.

## Checks

Current batch: 166 Python/browser tests passed, 4 opt-in Docker tests skipped in
the full suite. Those four Docker tests also passed in their separate live invocation.
Four JavaScript state tests passed.

```sh
.venv/bin/python -m pytest -q
node --test tests/frontend_state.test.mjs
# Optional browser tests:
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
TRACEROOT_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/test_workspace_browser.py -q
# Against an operator-owned disposable Docker session:
TRACEROOT_TEST_SESSION=/path/to/session .venv/bin/python -m pytest tests/test_docker_integration.py -q
.venv/bin/python -m traceroot workspace-ui --port 8875
```

Start from a WSL login shell with Docker/Azure CLI on PATH.
TRACEROOT_DOCKER_BINARY can explicitly identify Docker.
Provider credentials remain local, never browser settings.
