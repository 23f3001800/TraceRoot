"""Loopback-only approval dashboard for one exact remediation patch."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from .agents.approval import ApprovalRecord, patch_hash, save_approval

def serve_approval(context, patch_path: Path, investigation_id: str, port: int = 8765):
    patch=patch_path.read_text(encoding="utf-8"); digest=patch_hash(patch)
    ui_root=Path(__file__).parent.parent/"ui"
    payload={"investigation":investigation_id,"repository":context.repository.source,"session":context.config["id"],"hash":digest,"patch":patch}
    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,body,content_type):
            self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=="/api/approval-context": return self.respond(200,json.dumps(payload).encode(),"application/json")
            name={" /":"index.html"}.get(self.path,"")
            if self.path=="/": name="index.html"
            elif self.path.startswith("/ui/"): name=self.path.removeprefix("/ui/")
            file=(ui_root/name).resolve()
            if ui_root not in file.parents or not file.is_file(): return self.respond(404,b"Not found","text/plain")
            kind="text/css" if file.suffix==".css" else "application/javascript" if file.suffix==".js" else "text/html; charset=utf-8"
            return self.respond(200,file.read_bytes(),kind)
        def do_POST(self):
            if self.path!="/api/approve": return self.respond(404,b"{}", "application/json")
            data=parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length","0")),4096)).decode())
            person=(data.get("approved_by") or [""])[0].strip()
            if not person or len(person)>80:return self.respond(400,json.dumps({"message":"Invalid approver."}).encode(),"application/json")
            approval_id="a"+datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            record=ApprovalRecord(approval_id,investigation_id,digest,context.repository.source,context.config["id"],person,datetime.now(timezone.utc).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
            save_approval(context,record)
            return self.respond(200,json.dumps({"message":"Exact patch approved.","approval_id":approval_id}).encode(),"application/json")
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"TraceRoot approval UI: http://127.0.0.1:{port}",flush=True);server.serve_forever()
