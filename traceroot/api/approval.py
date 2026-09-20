"""Loopback exact-patch approval API using HTTP actions and replayable SSE."""
from __future__ import annotations
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from ..agents.approval import ApprovalRecord, patch_hash, save_approval
from ..public_data import public
from ..workspace_events import IncidentStore, valid_id


class ApprovalAPI:
    def __init__(self, context, patch_path, investigation_id):
        self.context = context
        self.patch = Path(patch_path).read_bytes().decode("utf-8")
        if public(self.patch) != self.patch:
            raise ValueError("Patch exceeds the public review limit or contains secret-like content.")
        self.investigation_id = valid_id(investigation_id)
        self.digest = patch_hash(self.patch)
        self.store = IncidentStore(context.session_dir / "approval-events")
        self._lock = threading.Lock()
        self.store._emit("approval.context", self.payload(), investigation_id)

    def payload(self):
        return {"type": "approval_context", "investigation": self.investigation_id,
                "repository": self.context.repository.source, "session": self.context.config["id"],
                "hash": self.digest, "patch": self.patch}

    def approve(self, person, digest):
        if digest != self.digest:
            raise ValueError("Patch changed. Reload and review the current patch.")
        if not isinstance(person, str) or not person.strip() or len(person) > 80:
            raise ValueError("Invalid approver.")
        with self._lock:
            prior = [e for e in self.store.replay(investigation_id=self.investigation_id)
                     if e["type"] == "approval.created" and e["data"].get("hash") == digest]
            if prior:
                raise ValueError("This patch already has an approval. Review its existing record.")
            now = datetime.now(timezone.utc)
            approval_id = uuid4().hex
            save_approval(self.context, ApprovalRecord(
                approval_id, self.investigation_id, self.digest, self.context.repository.source,
                self.context.config["id"], person.strip(), now.isoformat(),
                (now + timedelta(hours=1)).isoformat()))
            result = {"type": "approval_created", "message": "Exact patch approved.",
                      "approval_id": approval_id, "hash": digest}
            self.store._emit("approval.created", result, self.investigation_id)
            return result

    def handler(self, ui_root):
        api, ui_root = self, ui_root.resolve()
        class Handler(BaseHTTPRequestHandler):
            def reply(self, status, data, kind="application/json"):
                if not isinstance(data, bytes):
                    data = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def trusted(self):
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                return host.split(":")[0] in {"localhost", "127.0.0.1"} and (
                    not origin or origin == "http://" + host)

            def do_GET(self):
                if not self.trusted():
                    return self.reply(403, {"message": "Loopback origin required."})
                url = urlsplit(self.path)
                if url.path == "/api/approval-context":
                    return self.reply(200, api.payload())
                if url.path == "/api/events":
                    cursor = self.headers.get("Last-Event-ID", "")
                    try:
                        api.store.replay(cursor)
                    except ValueError:
                        return self.reply(400, {"message": "Invalid event cursor."})
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    try:
                        while True:
                            batch = api.store.replay(cursor, api.investigation_id)
                            for event in batch:
                                self.wfile.write(f"id: {event['id']}\nevent: trace\ndata: {json.dumps(event)}\n\n".encode())
                                cursor = event["id"]
                            if not batch:
                                self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
                            time.sleep(0.5)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                name = "index.html" if url.path == "/" else url.path.removeprefix("/ui/")
                path = (ui_root / name).resolve()
                if ui_root not in path.parents or not path.is_file():
                    return self.reply(404, {"message": "Not found."})
                kind = {".js": "application/javascript", ".css": "text/css"}.get(path.suffix, "text/html; charset=utf-8")
                return self.reply(200, path.read_bytes(), kind)

            def do_POST(self):
                if not self.trusted():
                    return self.reply(403, {"message": "Loopback origin required."})
                if self.path != "/api/approve":
                    return self.reply(404, {"message": "Unavailable action."})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 4096:
                        raise ValueError("Invalid request size.")
                    data = parse_qs(self.rfile.read(size).decode())
                    return self.reply(200, api.approve(
                        (data.get("approved_by") or [""])[0], (data.get("patch_hash") or [""])[0]))
                except (ValueError, TypeError) as exc:
                    return self.reply(400, {"message": str(exc)})

            def log_message(self, *_args):
                pass
        return Handler


def serve_approval(context, patch_path, investigation_id, port=8765):
    api = ApprovalAPI(context, patch_path, investigation_id)
    ui_root = Path(__file__).parents[2] / "ui"
    http = ThreadingHTTPServer(("127.0.0.1",port), api.handler(ui_root))
    print("TraceRoot approval UI: http://127.0.0.1:" + str(port), flush=True)
    http.serve_forever()
