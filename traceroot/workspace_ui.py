"""Loopback incident workspace with semantic SSE events and explicit operator actions."""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

from .agents.state import atomic_json


class IncidentStore:
    """Durable local reports and a fan-out stream of concise public events."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._listeners: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def _emit(self, event_type: str, data: dict) -> dict:
        event = {
            "id": uuid4().hex[:12],
            "type": event_type,
            "at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        with self._lock:
            with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event) + "\n")
            for listener in list(self._listeners):
                listener.put(event)
        return event

    def subscribe(self) -> queue.Queue:
        listener: queue.Queue = queue.Queue()
        with self._lock:
            self._listeners.add(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def create(
        self, repository: str, report: str, reproduction_command: str = ""
    ) -> dict:
        if not isinstance(repository, str) or not repository.strip() or len(repository) > 1024:
            raise ValueError("repository")
        if not isinstance(report, str) or not report.strip() or len(report) > 4000:
            raise ValueError("report")
        if not isinstance(reproduction_command, str) or len(reproduction_command) > 1000:
            raise ValueError("reproduction")

        item = {
            "id": uuid4().hex[:12],
            "repository": repository.strip(),
            "report": report.strip(),
            "reproduction_command": reproduction_command.strip(),
            "status": "REPORTED",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(self.root / f"{item['id']}.json", item)
        self._emit("incident.reported", {"incident": item})
        return item

    def list(self) -> list[dict]:
        records = []
        for path in self.root.glob("*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def action(self, kind: str, message: str = "") -> dict:
        allowed = {"run.message", "run.pause_requested", "run.resume_requested"}
        if kind not in allowed:
            raise ValueError("action")
        if not isinstance(message, str) or len(message) > 2000:
            raise ValueError("message")
        return self._emit(kind, {"message": message.strip(), "active_run": None})


class WorkspaceAPI:
    def __init__(self, root: Path):
        self.store = IncidentStore(root)

    def payload(self) -> dict:
        return {"type": "incidents", "items": self.store.list()}

    def handler(self, ui_root: Path):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, status: int, data: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def form_body(self) -> dict[str, list[str]]:
                size = min(int(self.headers.get("Content-Length", "0")), 7000)
                return parse_qs(self.rfile.read(size).decode("utf-8"))

            def do_GET(self) -> None:
                if self.path == "/api/incidents":
                    return self.reply(
                        200, json.dumps(api.payload()).encode("utf-8"), "application/json"
                    )
                if self.path == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    listener = api.store.subscribe()
                    try:
                        initial = {
                            "type": "workspace.ready",
                            "at": datetime.now(timezone.utc).isoformat(),
                            "data": {"active_run": None},
                        }
                        self.wfile.write(
                            f"event: trace\ndata: {json.dumps(initial)}\n\n".encode("utf-8")
                        )
                        self.wfile.flush()
                        while True:
                            try:
                                event = listener.get(timeout=15)
                                payload = (
                                    f"event: trace\ndata: {json.dumps(event)}\n\n".encode("utf-8")
                                )
                            except queue.Empty:
                                payload = b": keepalive\n\n"
                            self.wfile.write(payload)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        api.store.unsubscribe(listener)
                    return

                relative = (
                    "index.html"
                    if self.path == "/"
                    else self.path.removeprefix("/workspace/")
                    if self.path.startswith("/workspace/")
                    else ""
                )
                file_path = (ui_root / relative).resolve()
                if ui_root not in file_path.parents or not file_path.is_file():
                    return self.reply(404, b"Not found", "text/plain")
                content_type = {
                    ".css": "text/css",
                    ".js": "application/javascript",
                }.get(file_path.suffix, "text/html; charset=utf-8")
                return self.reply(200, file_path.read_bytes(), content_type)

            def do_POST(self) -> None:
                form = self.form_body()
                if self.path == "/api/incidents":
                    try:
                        item = api.store.create(
                            (form.get("repository") or [""])[0],
                            (form.get("report") or [""])[0],
                            (form.get("reproduction_command") or [""])[0],
                        )
                    except ValueError:
                        return self.reply(
                            400,
                            b'{"message":"Provide a repository and incident report."}',
                            "application/json",
                        )
                    return self.reply(
                        201, json.dumps({"item": item}).encode("utf-8"), "application/json"
                    )

                routes = {
                    "/api/messages": "run.message",
                    "/api/pause": "run.pause_requested",
                    "/api/resume": "run.resume_requested",
                }
                if self.path in routes:
                    try:
                        event = api.store.action(
                            routes[self.path], (form.get("message") or [""])[0]
                        )
                    except ValueError:
                        return self.reply(
                            400, b'{"message":"Invalid operator action."}', "application/json"
                        )
                    return self.reply(
                        202, json.dumps({"event": event}).encode("utf-8"), "application/json"
                    )
                return self.reply(404, b"{}", "application/json")

            def log_message(self, *_args) -> None:
                pass

        return Handler


def serve_workspace(root: Path, port: int = 8875) -> None:
    api = WorkspaceAPI(root)
    ui_root = Path(__file__).parents[1] / "workspace_ui"
    server = ThreadingHTTPServer(("127.0.0.1", port), api.handler(ui_root))
    print(
        f"TraceRoot workspace: http://127.0.0.1:{port} "
        f"SSE: http://127.0.0.1:{port}/api/events",
        flush=True,
    )
    server.serve_forever()
