"""Durable human approval records bound to one patch and sandbox session."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
from ..agents.state import atomic_json

@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str; investigation_id: str; approved_patch_hash: str
    repository: str; session_id: str; approved_by: str; approved_at: str
    expires_at: str; status: str = "APPROVED"; consumed_at: str | None = None

def patch_hash(patch: str) -> str: return hashlib.sha256(patch.encode("utf-8")).hexdigest()
def approval_path(context, approval_id: str) -> Path: return context.session_dir / "approvals" / f"{approval_id}.json"
def save_approval(context, record: ApprovalRecord) -> None:
    if not record.approval_id.isalnum() or len(record.approval_id) > 64: raise ValueError("Invalid approval ID.")
    path=approval_path(context,record.approval_id); path.parent.mkdir(mode=0o700,exist_ok=True); atomic_json(path,asdict(record))
def load_approval(context, approval_id: str) -> ApprovalRecord:
    path=approval_path(context,approval_id)
    if not path.is_file(): raise ValueError("Unknown approval.")
    return ApprovalRecord(**json.loads(path.read_text()))
def valid_now(value: str) -> bool: return datetime.fromisoformat(value.replace("Z","+00:00")) > datetime.now(timezone.utc)
