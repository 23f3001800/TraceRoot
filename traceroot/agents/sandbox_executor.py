"""Approval-bound future write boundary; patch application remains disabled."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..contracts import ToolFailure
from ..docker_runtime import require_active, container_options, docker
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
def docker_apply_check(context, request) -> dict:
 validate_execution_request(context, request)
 name = f"traceroot-apply-check-{context.config['id']}"
 result = docker(context, ["run", "--rm", *container_options(context, name), context.config["image"], "git", "apply", "--check", "--whitespace=error-all", "-"], timeout=30, input_bytes=request.patch.encode(), limit=8192)
 if result.timed_out: raise ToolFailure("patch_check_timeout", "Docker patch dry-run timed out.", "timeout")
 if result.exit_code: raise ToolFailure("patch_rejected", "Docker git apply --check rejected the patch.")
 return {"status": "PATCH_CHECKED", "approval_id": request.approval_id, "patch_hash": patch_hash(request.patch)}
def execute_approved_patch(context,request):
 docker_apply_check(context,request); raise ToolFailure("execution_not_enabled","Patch application is not enabled until the next ordered step.","unavailable")
