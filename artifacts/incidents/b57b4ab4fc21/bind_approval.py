"""Bind the operator's explicit approval to the disposable EduForge session."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets

from traceroot.agents.approval import ApprovalRecord, patch_hash, save_approval
from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
session = root / ".traceroot-runs" / "eduforgeb57b"
session.mkdir(parents=True, exist_ok=True)
snapshot = session / "snapshot"
snapshot.mkdir(exist_ok=True)
config = {
    "id": "eduforgeb57b",
    "repository": "/tmp/eduforge-gradeband-approval-check-b57b4ab4fc21",
    "snapshot": str(snapshot),
    "manifest": {},
    "docker": "/mnt/c/Program Files/Docker/Docker/resources/bin/docker",
    "runner": "docker",
    "image": "traceroot-investigation:eduforgeb57b",
    "network": "traceroot-eduforgeb57b",
    "db": "traceroot-db-eduforgeb57b",
    "api": "traceroot-api-eduforgeb57b",
    "active": True,
    "pythonpath": "/repo/backend:/opt/traceroot",
    "app_password": secrets.token_hex(16),
    "inspector_password": secrets.token_hex(16),
    "admin_password": secrets.token_hex(16),
}
context = Context(config, session)
context.save()
patch = (root / "artifacts/incidents/b57b4ab4fc21/proposed.patch").read_text()
now = datetime.now(timezone.utc)
record = ApprovalRecord(
    approval_id="b57b4ab4fc21approval",
    investigation_id="b57b4ab4fc21",
    approved_patch_hash=patch_hash(patch),
    repository=config["repository"],
    session_id=config["id"],
    approved_by="vikas-explicit-chat-approval",
    approved_at=now.isoformat(),
    expires_at=(now + timedelta(hours=1)).isoformat(),
)
save_approval(context, record)
print(record.approval_id, record.approved_patch_hash, record.session_id)
