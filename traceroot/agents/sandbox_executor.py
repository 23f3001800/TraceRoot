"""Future write boundary: validates an approved proposal before any sandbox action."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..contracts import ToolFailure
from ..docker_runtime import require_active

@dataclass(frozen=True)
class ExecutionRequest:
    approval_id: str
    repository: str
    patch: str
    plan: dict

def validate_execution_request(context, request: ExecutionRequest) -> None:
    if context.config.get("runner") != "docker":
        raise ToolFailure("docker_required", "Autonomous remediation requires DockerRunner.", "rejected")
    require_active(context)
    if not request.approval_id or len(request.approval_id) > 128:
        raise ToolFailure("approval_required", "A valid human approval ID is required.", "rejected")
    if Path(request.repository).resolve() != Path(context.repository.source).resolve():
        raise ToolFailure("repository_denied", "Execution repository is not this disposable session.", "rejected")
    if not request.patch.startswith("diff --git ") or len(request.patch) > 65536:
        raise ToolFailure("invalid_patch", "Execution accepts one bounded unified diff.", "rejected")

def execute_approved_patch(context, request: ExecutionRequest) -> dict:
    validate_execution_request(context, request)
    raise ToolFailure("execution_not_enabled", "Sandbox patch execution is intentionally not enabled yet.", "unavailable")
