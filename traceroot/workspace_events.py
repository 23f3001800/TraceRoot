"""Ordered, cross-process event journal and incident records for the workspace."""
import fcntl
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agents.state import atomic_json
from .public_data import public


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("Invalid investigation ID.")
    return value


class IncidentStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.journal = self.root / "events.jsonl"

    def _emit(self, event_type, data, investigation_id=None, stage=None):
        iid = investigation_id or data.get("incident_id") or data.get("investigation_id") or data.get("run_id") or "workspace"
        valid_id(iid)
        with (self.root / ".events.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            old = self.replay()
            sequence = 1 + sum(e.get("investigation_id") == iid for e in old)
            event = {"id": str(int(old[-1]["id"]) + 1 if old else 1),
                     "investigation_id": iid, "sequence": sequence, "type": event_type,
                     "at": datetime.now(timezone.utc).isoformat(),
                     "stage": stage or data.get("stage") or "Investigation", "data": public(data)}
            with self.journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=True) + "\n")
                stream.flush()
                import os
                os.fsync(stream.fileno())
            return event

    def replay(self, after="", investigation_id=None):
        if not self.journal.exists():
            return []
        events = []
        for line in self.journal.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue  # A partially written last line is picked up on the next read.
            if str(e.get("id", "")).isdigit():
                events.append(e)
        if after:
            if not str(after).isdigit():
                raise ValueError("Invalid event cursor.")
            events = [e for e in events if int(e["id"]) > int(after)]
        return [e for e in events if not investigation_id or e.get("investigation_id") == investigation_id]

    def create(self, repository, report, reproduction_command="", runtime=""):
        for value, limit in ((repository, 1024), (report, 4000), (reproduction_command, 1000), (runtime, 500)):
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("Invalid incident input.")
        if not report.strip() or not (repository.strip() or runtime.strip()):
            raise ValueError("Provide a report and repository or configured runtime.")
        item = {"id": uuid4().hex[:12], "repository": repository.strip(), "report": report.strip(),
                "reproduction_command": reproduction_command.strip(), "runtime": runtime.strip(),
                "status": "REPORTED", "created_at": datetime.now(timezone.utc).isoformat()}
        self.save(item)
        self._emit("incident.reported", {"incident": item}, item["id"], "Incident intake")
        return item

    def save(self, item):
        atomic_json(self.root / (valid_id(item["id"]) + ".json"), item)

    def get(self, iid):
        path = self.root / (valid_id(iid) + ".json")
        if not path.is_file():
            raise ValueError("Incident not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self):
        items = []
        for path in self.root.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if all(k in item for k in ("id", "report", "created_at")):
                    items.append(item)
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda i: i["created_at"], reverse=True)

    def action(self, kind, message=""):
        if kind not in {"run.message", "run.pause_requested", "run.resume_requested"} or len(message) > 2000:
            raise ValueError("Invalid operator action.")
        return self._emit(kind, {"message": message.strip()})


class WorkspaceProgress:
    NODES = {"reproduce": "Reproduction", "collect_runtime_evidence": "Runtime evidence",
             "investigate": "Investigation", "hypothesis_update": "Investigation",
             "evidence_auditor": "Evidence audit", "root_cause_report": "Root cause",
             "investigate_missing_evidence": "Investigation", "finalize": "PR / Report"}

    def __init__(self, root, investigation_id=None):
        self.store = IncidentStore(root)
        self.investigation_id = investigation_id
        self.run_id = None

    def __call__(self, progress):
        if self.investigation_id and progress.get("run_id") and progress["run_id"] != self.run_id:
            from .workspace_control import ActiveRuns
            self.run_id = progress["run_id"]
            ActiveRuns(self.store.root).update(self.investigation_id, run_id=self.run_id)
        name = progress.get("event", "agent.message")
        stage = self.NODES.get(progress.get("node"), progress.get("stage", "Investigation"))
        data = {k: v for k, v in progress.items() if k not in {"event", "arguments", "transcript", "prompt"}}
        if name == "graph_transition":
            data["label"] = stage
            name = "checkpoint.saved"
            if progress.get("node") == "evidence_auditor" and not self.investigation_id:
                name, data["label"] = "agent.started", "Evidence Auditor"
        else:
            name = {"provider_failure": "provider.error", "tool_selected": "tool.started",
                    "tool_result": "tool.completed"}.get(name, name)
        self.store._emit(name, data, self.investigation_id or progress.get("run_id"), stage)
