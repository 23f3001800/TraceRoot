"""Local-only human approval interface for one exact remediation patch."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from .agents.approval import ApprovalRecord, patch_hash, save_approval

def serve_approval(context, patch_path: Path, investigation_id: str, port: int = 8765):
    patch = patch_path.read_text(encoding="utf-8")
    digest = patch_hash(patch)
    class Handler(BaseHTTPRequestHandler):
        def send_html(self, body, status=200):
            data=body.encode(); self.send_response(status); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            self.send_html(f"""<!doctype html><title>TraceRoot approval</title><h1>Approve remediation</h1>
<p><b>Investigation:</b> {escape(investigation_id)}<br><b>Repository:</b> {escape(context.repository.source)}<br><b>Sandbox session:</b> {escape(context.config["id"])}<br><b>Patch SHA-256:</b> <code>{digest}</code></p>
<pre>{escape(patch)}</pre><form method="post"><label>Approver <input name="approved_by" required maxlength="80"></label><button type="submit">Approve exact patch</button></form>""")
        def do_POST(self):
            size=int(self.headers.get("Content-Length","0"))
            values=parse_qs(self.rfile.read(min(size,4096)).decode())
            person=(values.get("approved_by") or [""])[0].strip()
            if not person or len(person)>80: return self.send_html("<h1>Invalid approver</h1>",400)
            approval_id=f"a{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            record=ApprovalRecord(approval_id,investigation_id,digest,context.repository.source,context.config["id"],person,datetime.now(timezone.utc).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
            save_approval(context,record)
            self.send_html(f"<h1>Approved</h1><p>Approval ID: <code>{approval_id}</code></p><p>Patch hash: <code>{digest}</code></p>")
        def log_message(self, format, *args): pass
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"TraceRoot approval UI: http://127.0.0.1:{port}",flush=True)
    server.serve_forever()
