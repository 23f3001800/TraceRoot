"""Durable human approvals bound to patches, target actions, and sessions."""
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

@dataclass(frozen=True)
class TargetCommitApproval:
    approval_id: str; investigation_id: str; target_repository: str; session_id: str
    approved_action_hash: str; approved_by: str; approved_at: str; expires_at: str
    status: str = "APPROVED"; consumed_at: str | None = None

@dataclass(frozen=True)
class DeploymentApproval:
    approval_id: str; investigation_id: str; session_id: str
    approved_action_hash: str; approved_by: str; approved_at: str; expires_at: str
    status: str = "APPROVED"; consumed_at: str | None = None

def patch_hash(patch: str) -> str: return hashlib.sha256(patch.encode("utf-8")).hexdigest()

def commit_action_hash(repository: str, patch: str, branch: str, commit_message: str, verification: dict) -> str:
    payload = {"repository": str(Path(repository).resolve()), "patch_hash": patch_hash(patch),
               "branch": branch, "commit_message": commit_message,
               "verification_status": verification.get("status")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def deployment_action_hash(payload: dict) -> str:
    allowed = {
        "resource_group", "app_name", "slot", "commit", "artifact_sha256",
        "verification_status", "ci_status", "health_urls", "create_slot",
    }
    bounded = {key: payload[key] for key in sorted(allowed)}
    return hashlib.sha256(json.dumps(bounded, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def approval_path(context, approval_id: str) -> Path: return context.session_dir / "approvals" / f"{approval_id}.json"
def target_commit_approval_path(context, approval_id: str) -> Path: return context.session_dir / "target-commit-approvals" / f"{approval_id}.json"
def deployment_approval_path(context, approval_id: str) -> Path: return context.session_dir / "deployment-approvals" / f"{approval_id}.json"

def _valid_id(approval_id: str) -> None:
    if not approval_id.isalnum() or len(approval_id) > 64: raise ValueError("Invalid approval ID.")

def save_approval(context, record: ApprovalRecord) -> None:
    _valid_id(record.approval_id)
    path=approval_path(context,record.approval_id); path.parent.mkdir(mode=0o700,exist_ok=True); atomic_json(path,asdict(record))
def load_approval(context, approval_id: str) -> ApprovalRecord:
    _valid_id(approval_id)
    path=approval_path(context,approval_id)
    if not path.is_file(): raise ValueError("Unknown approval.")
    return ApprovalRecord(**json.loads(path.read_text()))
def valid_now(value: str) -> bool: return datetime.fromisoformat(value.replace("Z","+00:00")) > datetime.now(timezone.utc)

def consume_approval(context, approval_id: str) -> ApprovalRecord:
    record = load_approval(context, approval_id)
    if record.status != "APPROVED" or record.consumed_at:
        raise ValueError("Approval is not consumable.")
    consumed = ApprovalRecord(**{**asdict(record), "status": "CONSUMED", "consumed_at": datetime.now(timezone.utc).isoformat()})
    save_approval(context, consumed)
    return consumed

def save_target_commit_approval(context, record: TargetCommitApproval) -> None:
    _valid_id(record.approval_id)
    path=target_commit_approval_path(context,record.approval_id); path.parent.mkdir(mode=0o700,exist_ok=True); atomic_json(path,asdict(record))
def load_target_commit_approval(context, approval_id: str) -> TargetCommitApproval:
    _valid_id(approval_id)
    path=target_commit_approval_path(context,approval_id)
    if not path.is_file(): raise ValueError("Unknown target commit approval.")
    return TargetCommitApproval(**json.loads(path.read_text()))
def consume_target_commit_approval(context, approval_id: str) -> TargetCommitApproval:
    record=load_target_commit_approval(context,approval_id)
    if record.status != "APPROVED" or record.consumed_at: raise ValueError("Target commit approval is not consumable.")
    consumed=TargetCommitApproval(**{**asdict(record),"status":"CONSUMED","consumed_at":datetime.now(timezone.utc).isoformat()})
    save_target_commit_approval(context,consumed)
    return consumed

def save_deployment_approval(context, record: DeploymentApproval) -> None:
    _valid_id(record.approval_id)
    path=deployment_approval_path(context,record.approval_id); path.parent.mkdir(mode=0o700,exist_ok=True); atomic_json(path,asdict(record))
def load_deployment_approval(context, approval_id: str) -> DeploymentApproval:
    _valid_id(approval_id)
    path=deployment_approval_path(context,approval_id)
    if not path.is_file(): raise ValueError("Unknown deployment approval.")
    return DeploymentApproval(**json.loads(path.read_text()))
def consume_deployment_approval(context, approval_id: str) -> DeploymentApproval:
    record=load_deployment_approval(context,approval_id)
    if record.status != "APPROVED" or record.consumed_at: raise ValueError("Deployment approval is not consumable.")
    consumed=DeploymentApproval(**{**asdict(record),"status":"CONSUMED","consumed_at":datetime.now(timezone.utc).isoformat()})
    save_deployment_approval(context,consumed)
    return consumed
