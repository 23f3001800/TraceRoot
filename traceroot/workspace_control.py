"""Durable, loopback-only control records for workspace-launched investigations."""
from __future__ import annotations

import json
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from .agents.state import atomic_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActiveRuns:
    """Keeps process handles in memory and operator intent in the session directory."""

    def __init__(self, root: Path):
        self.root = root
        self._runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, incident_id: str, process: subprocess.Popen, session: Path, command: list[str]) -> dict:
        record = {"incident_id": incident_id, "pid": process.pid, "session": str(session),
                  "command": command, "status": "RUNNING", "started_at": _now()}
        with self._lock:
            self._runs[incident_id] = {**record, "process": process}
        atomic_json(self.root / f"run-{incident_id}.json", record)
        return record

    def _record(self, incident_id: str) -> dict:
        with self._lock:
            run = self._runs.get(incident_id)
            if run:
                return run
        path = self.root / f"run-{incident_id}.json"
        if not path.is_file():
            raise ValueError("active_run")
        return json.loads(path.read_text(encoding="utf-8"))

    def latest(self) -> str:
        with self._lock:
            candidates = list(self._runs.values())
        if not candidates:
            candidates = [json.loads(path.read_text(encoding="utf-8")) for path in self.root.glob("run-*.json")]
        if not candidates:
            raise ValueError("active_run")
        return max(candidates, key=lambda item: item.get("started_at", ""))["incident_id"]

    def control(self, kind: str, message: str = "", incident_id: str = "") -> dict:
        if kind not in {"message", "pause", "resume", "stop"}:
            raise ValueError("action")
        incident_id = incident_id or self.latest()
        run = self._record(incident_id)
        session = Path(run["session"])
        payload = {"kind": kind, "message": message, "incident_id": incident_id, "at": _now()}
        with (session / "operator-events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload) + "\n")
        control_path = session / "operator-control.json"
        if kind == "message":
            return payload
        if kind == "pause":
            atomic_json(control_path, {"state": "PAUSE_REQUESTED", **payload})
        elif kind == "stop":
            atomic_json(control_path, {"state": "STOP_REQUESTED", **payload})
            process = run.get("process")
            if process and process.poll() is None:
                process.send_signal(signal.SIGINT)
        else:
            atomic_json(control_path, {"state": "RUNNING", **payload})
        return payload

    def finished(self, incident_id: str, returncode: int) -> None:
        try:
            record = self._record(incident_id)
        except ValueError:
            return
        record.pop("process", None)
        record.update({"status": "FINISHED", "returncode": returncode, "finished_at": _now()})
        atomic_json(self.root / f"run-{incident_id}.json", record)
