"""Capture the real TraceRoot home page with synthetic, non-sensitive data."""
from __future__ import annotations

from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright

from traceroot.workspace_ui import WorkspaceAPI

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "traceroot-home.png"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="traceroot-screenshot-") as temporary:
        api = WorkspaceAPI(temporary)
        incident = api.store.create(
            "/workspaces/target-app",
            "Bulk order requests fail after deployment",
            "pytest tests/test_orders.py -q",
            "",
            "langgraph",
        )
        iid = incident["id"]
        api.active_runs.update(
            iid,
            status="RUNNING",
            session="sandbox-demo",
            run_id="run-demo",
            summary={"model": "configured-model", "orchestrator": "langgraph"},
        )
        api.store._emit("run.started", {"session": "sandbox-demo"}, iid)
        api.store._emit("stage.changed", {"label": "Investigation"}, iid)
        api.store._emit("agent.started", {"label": "Investigator"}, iid)
        api.store._emit("tool.completed", {
            "tool": "read_logs", "duration_ms": 182,
            "message": "Collected bounded runtime evidence."
        }, iid)
        api.store._emit("evidence.added", {
            "id": "E-17", "title": "Runtime error log", "tool": "read_logs",
            "path": "service/orders", "result": {"status": "ok"}
        }, iid)
        api.store._emit("hypothesis.updated", {"hypotheses": [{
            "id": "H1", "claim": "A database invariant rejects discounted totals."
        }]}, iid)

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), api.handler(ROOT / "ui" / "workspace")
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1536, "height": 960}, device_scale_factor=1)
                page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle")
                page.screenshot(path=str(OUTPUT), full_page=False)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print(OUTPUT)


if __name__ == "__main__":
    main()
