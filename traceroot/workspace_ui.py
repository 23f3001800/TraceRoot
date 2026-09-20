"""Loopback HTTP actions and one replayable SSE stream for the full workspace."""
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .agents.state import atomic_json
from .public_data import public
from .workspace_control import ActiveRuns
from .workspace_events import IncidentStore, WorkspaceProgress, valid_id
from .workspace_metrics import usage_metrics, validate_pricing


class WorkspaceAPI:
    def __init__(self, root):
        self.store = IncidentStore(root)
        self.active_runs = ActiveRuns(self.store.root)
        self._actions = threading.RLock()

    def payload(self):
        return {"type": "incidents", "items": public(self.store.list())}

    def detail(self, iid):
        incident = self.store.get(iid)
        try:
            record = self.active_runs._record(iid)
        except ValueError:
            record = {}
        if record.get("status") in {"RUNNING", "STARTING", "PAUSE_REQUESTED", "STOP_REQUESTED"} and not self.active_runs.alive(record):
            record = self.active_runs.update(iid, status="INTERRUPTED")
        # Never expose process commands, raw checkpoints, transcripts, or credentials.
        fields = ("status", "session", "run_id", "summary", "final", "plan", "patch", "patch_hash",
                  "files", "verification", "limitation", "error", "publication", "approval_id")
        events = self.store.replay(investigation_id=iid)
        return {"incident": public(incident), "run": public({k: record[k] for k in fields if k in record}),
                "events": events, "metrics": usage_metrics(self.store.root, record, events)}

    def launch(self, iid, action):
        with self._actions:
            self.store.get(iid)
            try:
                record = self.active_runs._record(iid)
            except ValueError:
                record = {}
            if record and self.active_runs.alive(record):
                raise ValueError("An operation already owns this investigation.")
            if action == "investigate" and record:
                raise ValueError("This incident already has a run. Resume it or create a new incident.")
            if action == "resume":
                from .workspace_worker import checkpoint_path
                if record.get("status") not in {"PAUSED", "INTERRUPTED"}:
                    raise ValueError("Only a paused or interrupted investigation can resume.")
                state = json.loads(checkpoint_path(record).read_text())
                if state["phase"] == "stopped" or state.get("pending_action"):
                    raise ValueError("An unfinished tool cannot be replayed automatically. Create a new incident.")
                atomic_json(Path(record["session"]) / "operator-control.json", {"state": "RUNNING"})
            if action == "plan" and (record.get("final") or {}).get("status") != "ROOT_CAUSE_SUPPORTED":
                raise ValueError("Remediation requires an independently supported root cause.")
            if action == "execute" and record.get("status") != "APPROVED":
                raise ValueError("Execution requires exact-patch approval.")
            command = [sys.executable, "-m", "traceroot.workspace_worker", "--root", str(self.store.root),
                       "--incident", iid, "--action", action]
            self.active_runs.update(iid, status="STARTING", operation=action)
            self.store._emit("run.queued", {"action": action}, iid)
            try:
                with (self.store.root / f"run-{iid}.log").open("ab") as log:
                    process = subprocess.Popen(command, cwd=Path(__file__).parents[1], stdout=log, stderr=subprocess.STDOUT)
                self.active_runs.register(iid, process, record.get("session"), command)
            except OSError:
                self.active_runs.update(iid, status="FAILED")
                raise ValueError("Could not launch the investigation worker.") from None
            def reap():
                self.active_runs.finished(iid, process.wait())
            threading.Thread(target=reap, daemon=True).start()
            return {"incident_id": iid, "status": "QUEUED"}

    def validate_input(self, repository, report, reproduction, runtime):
        if len(report) > 1000:
            raise ValueError("Incident descriptions support at most 1000 characters.")
        if runtime:
            raise ValueError("No deployed runtime is configured for this workspace yet.")
        if not repository or (not repository.startswith("https://github.com/") and not Path(repository).expanduser().is_dir()):
            raise ValueError("Provide an accessible local directory or HTTPS GitHub repository URL.")
        if reproduction:
            args = shlex.split(reproduction)
            if not args or (args[0] != "pytest" and args[:3] != ["python", "-m", "pytest"]):
                raise ValueError("Reproduction supports bounded pytest commands only.")

    def start_investigation(self, repository, report, reproduction="", runtime="", incident_id=""):
        self.validate_input(repository, report, reproduction, runtime)
        item = self.store.get(incident_id) if incident_id else self.store.create(repository, report, reproduction, runtime)
        self.launch(item["id"], "investigate")
        return item

    def operator_action(self, action, message="", incident_id=""):
        if not incident_id:
            raise ValueError("Select an incident first.")
        if action == "resume":
            return self.launch(incident_id, "resume")
        data = self.active_runs.control(action, message, incident_id)
        event = "run.message" if action == "message" else "run." + action + "_requested"
        if action == "stop" and self.active_runs._record(incident_id)["status"] == "STOPPED":
            event = "run.stopped"
        return self.store._emit(event, data, incident_id)

    def approval(self, iid, data, approve):
        from .context import Context
        from .agents.approval import ApprovalRecord, patch_hash, save_approval
        with self._actions:
            record = self.active_runs._record(iid)
            if self.active_runs.alive(record):
                raise ValueError("Wait for the current operation to finish.")
            if record.get("status") != "AWAITING_APPROVAL":
                raise ValueError("No patch is awaiting approval.")
            if data.get("patch_hash") != patch_hash(record["patch"]):
                raise ValueError("Patch changed. Reload and review the current patch.")
            person = data.get("approved_by", "").strip()
            if not person or len(person) > 80:
                raise ValueError("Provide the approver name.")
            if approve:
                context = Context.load(Path(record["session"]))
                now = datetime.now(timezone.utc)
                approval_id = uuid4().hex
                save_approval(context, ApprovalRecord(approval_id, iid, record["patch_hash"],
                    context.repository.source, context.config["id"], person, now.isoformat(),
                    (now + timedelta(hours=1)).isoformat()))
                self.active_runs.update(iid, status="APPROVED", approval_id=approval_id)
            else:
                self.active_runs.update(iid, status="REJECTED")
            self.store._emit("approval.received", {"decision": "APPROVED" if approve else "REJECTED",
                              "patch_hash": record["patch_hash"], "approved_by": person}, iid, "Approval")
            return {"status": "APPROVED" if approve else "REJECTED"}

    def handler(self, ui_root):
        api = self
        ui_root = ui_root.resolve()
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
                if host.split(":")[0] not in {"127.0.0.1", "localhost"}:
                    return False
                origin = self.headers.get("Origin")
                return not origin or origin in {"http://" + host, "https://" + host}

            def do_GET(self):
                if not self.trusted():
                    return self.reply(403, {"message": "Loopback origin required."})
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                try:
                    if url.path == "/api/incidents":
                        return self.reply(200, api.payload())
                    if url.path == "/api/capabilities":
                        return self.reply(200, {"runtime_targets": [], "publish": False,
                            "limitations": ["Docker adapter supports pinned Python/FastAPI targets.",
                                           "Configure a runtime target before deployed investigation.",
                                           "External publishing is unavailable until a target and authorization are configured."]})
                    match = re.fullmatch(r"/api/incidents/([A-Za-z0-9_-]+)", url.path)
                    if match:
                        return self.reply(200, api.detail(match[1]))
                    if url.path == "/api/events":
                        iid = (query.get("investigation_id") or [None])[0]
                        if iid:
                            valid_id(iid)
                        cursor = self.headers.get("Last-Event-ID") or (query.get("after") or [""])[0]
                        api.store.replay(cursor, iid)  # Validate before committing HTTP headers.
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        try:
                            ready = json.dumps({"type": "workspace.ready", "data": {}})
                            self.wfile.write(("event: trace\ndata: " + ready + "\n\n").encode())
                            self.wfile.flush()
                            while True:
                                batch = api.store.replay(cursor, iid)
                                for event in batch:
                                    self.wfile.write(f"id: {event['id']}\nevent: trace\ndata: {json.dumps(event)}\n\n".encode())
                                    cursor = event["id"]
                                if not batch:
                                    self.wfile.write(b": heartbeat\n\n")
                                self.wfile.flush()
                                time.sleep(0.5)
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            pass
                        return
                    relative = "index.html" if url.path == "/" else url.path.removeprefix("/workspace/")
                    path = (ui_root / relative).resolve()
                    if ui_root not in path.parents or not path.is_file():
                        return self.reply(404, {"message": "Not found."})
                    kind = {".js": "application/javascript", ".mjs": "application/javascript", ".css": "text/css"}.get(path.suffix, "text/html; charset=utf-8")
                    return self.reply(200, path.read_bytes(), kind)
                except (ValueError, KeyError):
                    return self.reply(400, {"message": "Invalid request or unavailable incident."})

            def do_POST(self):
                if not self.trusted():
                    return self.reply(403, {"message": "Loopback origin required."})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 100000:
                        raise ValueError("Request body exceeds the limit.")
                    raw = self.rfile.read(size).decode("utf-8")
                    if self.headers.get("Content-Type", "").startswith("application/json"):
                        data = json.loads(raw)
                    else:
                        data = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
                    if not isinstance(data, dict):
                        raise ValueError("Expected an object.")
                    iid = data.get("incident_id", "")
                    if self.path == "/api/incidents":
                        item = api.store.create(data.get("repository", ""), data.get("report", ""),
                                                data.get("reproduction_command", ""), data.get("runtime", ""))
                        return self.reply(201, {"item": item})
                    if self.path == "/api/pricing":
                        rate = validate_pricing(data)
                        with api._actions:
                            path = api.store.root / "pricing.json"
                            prices = json.loads(path.read_text()) if path.exists() else {}
                            prices[rate["model"]] = rate
                            atomic_json(path, prices)
                        return self.reply(200, {"message": "Estimate rates saved.", "rate": rate})
                    if self.path == "/api/runs":
                        if iid:
                            item = api.store.get(iid)
                            api.validate_input(item["repository"], item["report"], item["reproduction_command"], item["runtime"])
                            api.launch(iid, "investigate")
                        else:
                            item = api.start_investigation(data.get("repository", ""), data.get("report", ""),
                                data.get("reproduction_command", ""), data.get("runtime", ""))
                        return self.reply(202, {"item": item})
                    action = self.path.removeprefix("/api/")
                    if action in {"messages", "pause", "resume", "stop"}:
                        result = api.operator_action("message" if action == "messages" else action, data.get("message", ""), iid)
                    elif action in {"plan", "execute"}:
                        result = api.launch(iid, action)
                    elif action in {"approve", "reject"}:
                        result = api.approval(iid, data, action == "approve")
                    elif action == "snapshot":
                        detail = api.detail(iid)
                        atomic_json(api.store.root / f"snapshot-{iid}-{uuid4().hex[:8]}.json", detail)
                        result = api.store._emit("checkpoint.snapshot", {"message": "Public investigation snapshot saved."}, iid)
                    else:
                        return self.reply(404, {"message": "Unavailable action."})
                    return self.reply(202, result)
                except (ValueError, KeyError, TypeError) as exc:
                    return self.reply(400, {"message": public(str(exc))})
                except OSError:
                    return self.reply(503, {"message": "Workspace storage or process unavailable."})

            def log_message(self, *_args):
                pass
        return Handler


def serve_workspace(root, port=8875):
    api = WorkspaceAPI(root)
    server = ThreadingHTTPServer(("127.0.0.1", port), api.handler(Path(__file__).parents[1] / "ui" / "workspace"))
    print(f"TraceRoot workspace: http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
