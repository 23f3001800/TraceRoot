"""Approval-bound deterministic Azure staging deployment; never targets production."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Callable
from urllib.request import Request, urlopen

from ..contracts import ToolFailure
from ..process import ProcessResult, run_process
from .approval import (
    consume_deployment_approval,
    deployment_action_hash,
    load_deployment_approval,
    valid_now,
)

_NAME = re.compile(r"[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
_SAFE_SLOTS = frozenset({"staging", "traceroot-recovery"})


@dataclass(frozen=True)
class StagingDeploymentRequest:
    investigation_id: str
    approval_id: str
    resource_group: str
    app_name: str
    slot: str
    commit: str
    artifact: str
    verification: dict
    ci_status: str
    health_urls: tuple[str, ...]
    create_slot: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def action_payload(request: StagingDeploymentRequest) -> dict:
    artifact = Path(request.artifact).resolve()
    return {
        "resource_group": request.resource_group,
        "app_name": request.app_name,
        "slot": request.slot,
        "commit": request.commit,
        "artifact_sha256": _sha256(artifact),
        "verification_status": request.verification.get("status"),
        "ci_status": request.ci_status,
        "health_urls": list(request.health_urls),
        "create_slot": request.create_slot,
    }


def _default_probe(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "TraceRoot-Verifier/1.0"})
    with urlopen(request, timeout=15) as response:
        return response.status == 200


def deploy_verified_staging(
    context,
    request: StagingDeploymentRequest,
    *,
    runner: Callable[..., ProcessResult] = run_process,
    probe: Callable[[str], bool] = _default_probe,
) -> dict:
    if request.slot not in _SAFE_SLOTS:
        raise ToolFailure("production_denied", "Only an isolated staging slot is allowed.")
    if not _NAME.fullmatch(request.resource_group) or not _NAME.fullmatch(request.app_name):
        raise ToolFailure("target_denied", "Azure target names are invalid.")
    if request.verification.get("status") != "FIX_VERIFIED":
        raise ToolFailure("verification_required", "Deployment requires FIX_VERIFIED.")
    if request.ci_status != "PASSED":
        raise ToolFailure("ci_required", "Deployment requires passing deterministic CI.")
    if not re.fullmatch(r"[0-9a-f]{40}", request.commit):
        raise ToolFailure("commit_denied", "Deployment requires an exact Git commit.")
    artifact = Path(request.artifact).resolve()
    if artifact.suffix != ".zip" or not artifact.is_file():
        raise ToolFailure("artifact_denied", "Deployment requires an existing ZIP artifact.")
    if not request.health_urls or any(not url.startswith("https://") for url in request.health_urls):
        raise ToolFailure("healthcheck_denied", "Bounded HTTPS health checks are required.")

    try:
        approval = load_deployment_approval(context, request.approval_id)
    except ValueError:
        raise ToolFailure("approval_unknown", "No matching deployment approval exists.") from None
    expected = deployment_action_hash(action_payload(request))
    if (
        approval.status != "APPROVED"
        or approval.consumed_at
        or not valid_now(approval.expires_at)
        or approval.investigation_id != request.investigation_id
        or approval.session_id != context.config["id"]
        or approval.approved_action_hash != expected
    ):
        raise ToolFailure("approval_scope_mismatch", "Approval does not cover this exact staging deployment.")

    consume_deployment_approval(context, request.approval_id)
    base = ["az", "webapp", "deployment", "slot"]
    if request.create_slot:
        created = runner(base + ["create", "--resource-group", request.resource_group,
                         "--name", request.app_name, "--slot", request.slot], 180)
        if created.exit_code or created.timed_out:
            raise ToolFailure("slot_creation_failed", "Approved staging slot creation failed.", "error")
    deployed = runner(
        ["az", "webapp", "deploy", "--resource-group", request.resource_group,
         "--name", request.app_name, "--slot", request.slot, "--type", "zip",
         "--src-path", str(artifact), "--clean", "true", "--restart", "true"],
        900,
    )
    if deployed.exit_code or deployed.timed_out:
        raise ToolFailure("deployment_failed", "Approved staging deployment failed.", "error")

    healthy = all(probe(url) for url in request.health_urls)
    if not healthy:
        runner(["az", "webapp", "stop", "--resource-group", request.resource_group,
                "--name", request.app_name, "--slot", request.slot], 120)
        return {"status": "STAGING_VERIFICATION_FAILED", "slot": request.slot,
                "commit": request.commit, "contained": True, "production_changed": False}
    return {"status": "STAGING_VERIFIED", "slot": request.slot, "commit": request.commit,
            "production_changed": False}
