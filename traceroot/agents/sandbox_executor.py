"""Approval-bound future write boundary; patch application remains disabled."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..contracts import ToolFailure
from ..docker_runtime import require_active, container_options, docker
from .approval import load_approval, patch_hash, valid_now, consume_approval
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
def execute_approved_patch(context, request):
    docker_apply_check(context, request)
    suffix = patch_hash(request.patch)[:12]
    container = f"traceroot-apply-{context.config['id']}-{suffix}"
    image = f"{context.config['image']}-patch-{suffix}"
    options = ["create", "--name", container, "--label", f"traceroot.session={context.config['id']}",
               "--network", "none", "--user", "0:0", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "--memory", "256m",
               "--cpus", "1", "--pids-limit", "64", "--workdir", "/repo",
               context.config["image"], "sleep", "30"]
    created = False
    try:
        result = docker(context, options, timeout=30, limit=8192)
        if result.exit_code: raise ToolFailure("patch_application_failed", "Could not create the disposable patch container.", "error")
        created = True
        result = docker(context, ["start", container], timeout=15, limit=8192)
        if result.exit_code: raise ToolFailure("patch_application_failed", "Could not start the disposable patch container.", "error")
        result = docker(context, ["exec", "-i", container, "git", "apply", "--whitespace=error-all", "-"], timeout=30, input_bytes=request.patch.encode(), limit=8192)
        if result.timed_out or result.exit_code: raise ToolFailure("patch_application_failed", "Docker git apply failed.", "error")
        result = docker(context, ["commit", "--pause", container, image], timeout=60, limit=8192)
        if result.exit_code: raise ToolFailure("patch_application_failed", "Could not create the patched sandbox image.", "error")
        context.config["base_image"] = context.config["image"]
        context.config["image"] = image
        context.config["patched_image"] = image
        context.save()
        consume_approval(context, request.approval_id)
        return {"status": "PATCH_APPLIED", "approval_id": request.approval_id, "patch_hash": patch_hash(request.patch), "image": image}
    finally:
        if created: docker(context, ["rm", "-f", container], timeout=10, limit=8192)

def rollback_patch(context) -> dict:
    patched = context.config.get("patched_image")
    base = context.config.get("base_image")
    if not patched or not base:
        raise ToolFailure("rollback_unavailable", "No derived patch image exists.", "rejected")
    result = docker(context, ["image", "rm", patched], timeout=30, limit=8192)
    if result.exit_code:
        raise ToolFailure("rollback_failed", "Could not remove the derived patch image.", "error")
    context.config["image"] = base
    context.config.pop("patched_image", None)
    context.config.pop("base_image", None)
    context.save()
    return {"status": "PATCH_ROLLED_BACK", "image": patched}

def destroy_sandbox(context) -> dict:
    from ..docker_runtime import cleanup
    patched = context.config.get("patched_image")
    base = context.config.get("base_image") or context.config.get("image")
    cleanup(context)
    removed=[]
    for image in (patched, base):
        if image and image.startswith(f"traceroot-investigation:{context.config['id']}") or (image and image.startswith(f"traceroot-investigation:{context.config['id']}-patch-")):
            result=docker(context, ["image", "rm", image], timeout=30, limit=8192)
            if result.exit_code: raise ToolFailure("destruction_failed", "Could not remove a session image.", "error")
            removed.append(image)
    return {"status":"SANDBOX_DESTROYED","images_removed":removed}
