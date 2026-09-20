"""Real Chromium + real HTTP/SSE; synthetic evidence stays inside this test's temp workspace."""
import os
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("TRACEROOT_BROWSER_TESTS") != "1",
                                reason="Opt in with TRACEROOT_BROWSER_TESTS=1 and install Playwright Chromium.")


def test_dashboard_save_history_evidence_snapshot_and_patch_rejection(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from traceroot.workspace_ui import WorkspaceAPI
    from traceroot.agents.approval import patch_hash
    api = WorkspaceAPI(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler(Path("ui/workspace")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.locator("#d-new").click()
            page.locator('input[name="repository"]').fill(str(tmp_path))
            page.locator('textarea[name="report"]').fill("Browser integration test incident")
            page.get_by_role("button", name="Save incident", exact=True).click()
            expect(page.locator("#d-title")).to_have_text("Browser integration test incident")
            expect(page.locator("#d-start-saved")).to_be_enabled()
            expect(page.locator("#d-pause")).to_be_disabled()
            item = api.store.list()[0]
            assert not list(tmp_path.glob("run-*.json")), "Saving must not start a process."
            api.store._emit("evidence.added", {"id": "E-1", "title": "Logs", "tool": "read_logs",
                                             "result": {"data": {"text": "first observation"}}}, item["id"])
            api.store._emit("evidence.added", {"id": "E-2", "title": "Source", "tool": "read_file",
                                             "result": {"data": {"text": "second observation"}}}, item["id"])
            expect(page.locator('#d-evidence [data-eid="E-2"]')).to_be_visible()
            page.locator("#d-search").fill("second observation")
            page.locator('#d-evidence [data-eid="E-2"]').click()
            expect(page.locator("#d-detail")).to_contain_text("second observation")
            page.reload()
            page.locator("#d-filters").click()
            expect(page.locator("#d-timeline .event")).to_have_count(3)
            page.locator("#d-tb-snapshot").click()
            expect(page.locator("#d-timeline .event")).to_have_count(4)
            assert list(tmp_path.glob("snapshot-*.json"))
            patch = "diff --git a/app/a.py b/app/a.py\n--- a/app/a.py\n+++ b/app/a.py\n@@ -1 +1 @@\n-old\n+new\n"
            api.active_runs.update(item["id"], status="AWAITING_APPROVAL", patch=patch,
                                   patch_hash=patch_hash(patch))
            api.store._emit("patch.ready", {"patch_hash": patch_hash(patch)}, item["id"])
            expect(page.locator("#d-patch")).to_contain_text("+new")
            expect(page.locator("#d-execute")).to_be_disabled()
            page.locator("#d-approver").fill("Browser tester")
            page.locator("#d-reject").click()
            expect(page.locator("#d-chip")).to_have_text("REJECTED")
            assert api.active_runs._record(item["id"])["status"] == "REJECTED"
            page.locator('[data-nav="history"]').click()
            expect(page.locator("#d-history-list")).to_contain_text(item["report"])
            page.locator("#d-history-close").click()
            page.set_viewport_size({"width": 800, "height": 1000})
            expect(page.locator("#d-right")).to_be_visible()
            assert errors == []
            page.locator('[data-nav="settings"]').click()
            page.locator('#d-pricing-form input[name="model"]').fill("example-model")
            page.locator('#d-pricing-form input[name="input_usd_per_million"]').fill("2")
            page.locator('#d-pricing-form input[name="output_usd_per_million"]').fill("8")
            page.get_by_role("button", name="Save pricing").click()
            expect(page.locator("#d-settings")).to_be_hidden()
            assert (tmp_path / "pricing.json").exists()
            expect(page.locator("#d-usage")).to_contain_text("model latency")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
