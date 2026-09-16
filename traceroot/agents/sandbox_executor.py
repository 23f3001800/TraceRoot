"""Approval-bound future write boundary; patch application remains disabled."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..contracts import ToolFailure
from ..docker_runtime import require_active
from .approval import load_approval, patch_hash, valid_now
from .patch_policy import validate_patch
@dataclass(frozen=True)
class ExecutionRequest:
 approval_id:str; repository:str; patch:str; plan:dict
def validate_execution_request(context,request):
 if context.config.get("runner")!="docker": raise ToolFailure("docker_required","Autonomous remediation requires DockerRunner.")
 require_active(context); validate_patch(request.patch)
 try: approval=load_approval(context,request.approval_id)
 except ValueError: raise ToolFailure("approval_unknown","No matching human approval exists.")
 if approval.status!="APPROVED" or approval.consumed_at or not valid_now(approval.expires_at): raise ToolFailure("approval_invalid","Approval is expired, consumed, or not active.")
 if approval.approved_patch_hash!=patch_hash(request.patch): raise ToolFailure("approval_patch_mismatch","Approval does not cover this exact patch.")
 if approval.repository!=str(Path(request.repository).resolve()) or approval.session_id!=context.config["id"]: raise ToolFailure("approval_scope_mismatch","Approval does not cover this repository session.")
 if Path(request.repository).resolve()!=Path(context.repository.source).resolve(): raise ToolFailure("repository_denied","Execution repository is not this disposable session.")
 return approval
def execute_approved_patch(context,request):
 validate_execution_request(context,request); raise ToolFailure("execution_not_enabled","Patch application remains disabled until Docker dry-run validation is implemented.","unavailable")
