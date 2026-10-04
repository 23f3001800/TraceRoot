"""PostgreSQL persistence for incidents, events, checkpoints, and approvals."""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from .public_data import public
from .workspace_events import valid_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS traceroot_incidents (
  id text PRIMARY KEY, payload jsonb NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS traceroot_events (
  id bigserial PRIMARY KEY, investigation_id text NOT NULL,
  sequence integer NOT NULL, event_type text NOT NULL, stage text NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL,
  UNIQUE (investigation_id, sequence)
);
CREATE TABLE IF NOT EXISTS traceroot_records (
  namespace text NOT NULL, record_id text NOT NULL, payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL, PRIMARY KEY (namespace, record_id)
);
"""

class PostgresStateStore:
    """Transaction-safe store; callers may inject a DB-API connection factory."""
    def __init__(self, dsn, connect=None, root=".traceroot-workspace"):
        if not isinstance(dsn, str) or not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("a PostgreSQL DSN is required")
        if connect is None:
            from psycopg import connect
        self.dsn, self.connect = dsn, connect
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def migrate(self):
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(SCHEMA)

    def save_record(self, namespace, record_id, payload):
        valid_id(record_id)
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO traceroot_records(namespace,record_id,payload,updated_at)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(namespace,record_id) DO UPDATE
                    SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at""",
                    (namespace, record_id, json.dumps(payload), datetime.now(timezone.utc)))

    def load_record(self, namespace, record_id):
        valid_id(record_id)
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM traceroot_records WHERE namespace=%s AND record_id=%s", (namespace, record_id))
                row = cursor.fetchone()
        if not row:
            raise ValueError("record not found")
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def save_evaluation(self, investigation_id, report):
        """Persist the immutable evaluation result alongside operational state."""
        self.save_record("evaluation", investigation_id, report)

    def load_evaluation(self, investigation_id):
        return self.load_record("evaluation", investigation_id)

    def save(self, item):
        valid_id(item["id"])
        created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO traceroot_incidents(id,payload,created_at) VALUES (%s,%s,%s)
                    ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload""",
                    (item["id"], json.dumps(item), created))

    def create(self, repository, report, reproduction_command="", runtime="", orchestrator="langgraph"):
        from .orchestrator import validate_orchestrator
        if not report.strip() or not (repository.strip() or runtime.strip()):
            raise ValueError("Provide a report and repository or configured runtime.")
        item = {"id":uuid4().hex[:12], "repository":repository.strip(), "report":report.strip(),
                "reproduction_command":reproduction_command.strip(), "runtime":runtime.strip(),
                "orchestrator":validate_orchestrator(orchestrator), "status":"REPORTED",
                "created_at":datetime.now(timezone.utc).isoformat()}
        self.save(item); self._emit("incident.reported", {"incident":item}, item["id"], "Incident intake")
        return item

    def get(self, iid):
        valid_id(iid)
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM traceroot_incidents WHERE id=%s", (iid,)); row = cursor.fetchone()
        if not row: raise ValueError("Incident not found.")
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def list(self):
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM traceroot_incidents ORDER BY created_at DESC"); rows = cursor.fetchall()
        return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]

    def _emit(self, event_type, data, investigation_id=None, stage=None):
        iid = investigation_id or data.get("incident_id") or "workspace"; valid_id(iid)
        now = datetime.now(timezone.utc)
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (iid,))
                cursor.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM traceroot_events WHERE investigation_id=%s", (iid,))
                sequence = cursor.fetchone()[0]
                cursor.execute("""INSERT INTO traceroot_events(investigation_id,sequence,event_type,stage,payload,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (iid, sequence, event_type, stage or data.get("stage") or "Investigation", json.dumps(public(data)), now))
                event_id = cursor.fetchone()[0]
        return {"id":str(event_id), "investigation_id":iid, "sequence":sequence, "type":event_type,
                "at":now.isoformat(), "stage":stage or data.get("stage") or "Investigation", "data":public(data)}

    def replay(self, after="", investigation_id=None):
        if after and not str(after).isdigit(): raise ValueError("Invalid event cursor.")
        query = "SELECT id,investigation_id,sequence,event_type,created_at,stage,payload FROM traceroot_events WHERE id>%s"
        params = [int(after or 0)]
        if investigation_id: query += " AND investigation_id=%s"; params.append(valid_id(investigation_id))
        query += " ORDER BY id"
        with self.connect(self.dsn) as connection:
            with connection.cursor() as cursor: cursor.execute(query, params); rows = cursor.fetchall()
        return [{"id":str(r[0]),"investigation_id":r[1],"sequence":r[2],"type":r[3],"at":r[4].isoformat(),"stage":r[5],"data":r[6] if isinstance(r[6],dict) else json.loads(r[6])} for r in rows]

def durable_store(dsn, connect=None, root=".traceroot-workspace"):
    store = PostgresStateStore(dsn, connect, root); store.migrate(); return store

def configured_store(root):
    """Use PostgreSQL when configured, retaining local files for process leases."""
    dsn = os.environ.get("TRACEROOT_DATABASE_URL", "").strip()
    if not dsn:
        from .workspace_events import IncidentStore
        return IncidentStore(root)
    return durable_store(dsn, root=root)
