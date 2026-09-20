"""Process ownership and durable operator requests; no agent-controlled writes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import threading
from uuid import uuid4

from .agents.state import atomic_json
from .workspace_events import valid_id


def now():
    return datetime.now(timezone.utc).isoformat()


def process_identity(pid):
    try:
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


class ActiveRuns:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._runs = {}
        self._lock = threading.RLock()

    @contextmanager
    def lock(self, iid):
        with self._lock, (self.root / f".run-{valid_id(iid)}.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def _record(self, iid):
        path = self.root / f"run-{valid_id(iid)}.json"
        if not path.is_file():
            raise ValueError("No run exists for this incident.")
        return json.loads(path.read_text())

    def update(self, iid, **changes):
        with self.lock(iid):
            try:
                record = self._record(iid)
            except ValueError:
                record = {"incident_id": iid, "started_at": now()}
            record.update(changes)
            record["updated_at"] = now()
            atomic_json(self.root / f"run-{iid}.json", record)
            return record

    def register(self, incident_id, process, session, command):
        with self._lock:
            self._runs[incident_id] = process
        changes = {"pid": process.pid, "process_identity": process_identity(process.pid), "command": command}
        if session:
            changes["session"] = str(session)
        try:
            self._record(incident_id)
        except ValueError:
            changes["status"] = "RUNNING"
        return self.update(incident_id, **changes)

    def latest(self):
        records = [json.loads(p.read_text()) for p in self.root.glob("run-*.json")]
        if len(records) != 1:
            raise ValueError("Select an incident before sending an operator action.")
        return records[0]["incident_id"]

    def alive(self, record):
        process = self._runs.get(record["incident_id"])
        if process:
            return process.poll() is None
        identity = record.get("process_identity")
        return bool(identity and identity == process_identity(record.get("pid")))

    def control(self, kind, message="", incident_id=""):
        iid = incident_id or self.latest()
        with self.lock(iid):
            run = self._record(iid)
            if kind not in {"message", "pause", "stop"}:
                raise ValueError("Invalid operator action.")
            if not isinstance(message, str) or len(message) > 2000 or (kind == "message" and not message.strip()):
                raise ValueError("Provide a message of at most 2000 characters.")
            if run.get("status") not in {"RUNNING", "PAUSE_REQUESTED", "PAUSED", "STARTING"}:
                raise ValueError("This investigation is not active.")
            if not run.get("session") and kind != "stop":
                raise ValueError("Wait for environment preparation to finish.")
            session = Path(run["session"]) if run.get("session") else None
            payload = {"id": uuid4().hex, "kind": kind, "message": message.strip(),
                       "incident_id": iid, "at": now()}
            if session:
                with (session / "operator-events.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(payload) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            if kind in {"pause", "stop"}:
                state = "PAUSE_REQUESTED" if kind == "pause" else "STOP_REQUESTED"
                if session:
                    atomic_json(session / "operator-control.json", {"state": state, **payload})
                if kind == "stop" and not self.alive(run):
                    state = "STOPPED"
                run["status"] = state
                atomic_json(self.root / f"run-{iid}.json", run)
            if kind == "stop":
                process = self._runs.get(iid)
                if process and process.poll() is None:
                    process.send_signal(signal.SIGINT)
                elif self.alive(run):
                    os.kill(run["pid"], signal.SIGINT)
            return payload

    def finished(self, iid, returncode):
        with self._lock:
            self._runs.pop(iid, None)
        record = self._record(iid)
        # The worker's terminal status, including PAUSED, is authoritative.
        changes = {"returncode": returncode, "finished_at": now()}
        if record.get("status") == "STOP_REQUESTED":
            changes["status"] = "STOPPED"
        elif record.get("status") in {"RUNNING", "STARTING", "PAUSE_REQUESTED"}:
            changes["status"] = "INTERRUPTED"
        return self.update(iid, **changes)
