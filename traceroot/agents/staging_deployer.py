"""Approval-bound deterministic Azure staging deployment; never targets production."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from time import sleep
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
    target_kind: str = "slot"
    service_plan: str | None = None
    app_settings: tuple[str, ...] = ()
    startup_command: str | None = None
    azure_timeout_ms: int | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def action_payload(request: StagingDeploymentRequest) -> dict:
    artifact = Path(request.artifact).resolve()
    payload = {
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
    if request.target_kind != "slot":
        payload.update(
            target_kind=request.target_kind,
            service_plan=request.service_plan,
            app_settings=list(request.app_settings),
            startup_command=request.startup_command,
        )
        if request.azure_timeout_ms is not None:
            payload["azure_timeout_ms"] = request.azure_timeout_ms
    return payload


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
    wait: Callable[[float], None] = sleep,
) -> dict:
    if request.target_kind == "slot":
        if request.slot not in _SAFE_SLOTS:
            raise ToolFailure("production_denied", "Only an isolated staging slot is allowed.")
    elif request.target_kind == "app":
        if not request.app_name.endswith("-staging") or not request.service_plan or not _NAME.fullmatch(request.service_plan):
            raise ToolFailure("production_denied", "A separate target must be an explicitly named staging app.")
        if request.app_settings != ("LLM_PROFILE=ci", "SCM_DO_BUILD_DURING_DEPLOYMENT=true"):
            raise ToolFailure("configuration_denied", "The isolated staging profile must use bounded replay settings.")
        if request.startup_command != "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend":
            raise ToolFailure("configuration_denied", "The staging startup command is not approved.")
    else:
        raise ToolFailure("target_denied", "Unknown staging target kind.")
    if not _NAME.fullmatch(request.resource_group) or not _NAME.fullmatch(request.app_name):
        raise ToolFailure("target_denied", "Azure target names are invalid.")
    if request.verification.get("status") != "FIX_VERIFIED":
        raise ToolFailure("verification_required", "Deployment requires FIX_VERIFIED.")
    if request.ci_status != "PASSED":
        raise ToolFailure("ci_required", "Deployment requires passing deterministic CI.")
    if request.azure_timeout_ms is not None and not 300000 <= request.azure_timeout_ms <= 1200000:
        raise ToolFailure("timeout_denied", "Azure deployment timeout must be five to twenty minutes.")
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
    if request.create_slot and request.target_kind == "slot":
        created = runner(["az", "webapp", "deployment", "slot", "create",
                          "--resource-group", request.resource_group,
                          "--name", request.app_name, "--slot", request.slot], 180)
        if created.exit_code or created.timed_out:
            raise ToolFailure("slot_creation_failed", "Approved staging slot creation failed.", "error")
    elif request.create_slot:
        created = runner(["az", "webapp", "create", "--resource-group", request.resource_group,
                          "--plan", request.service_plan, "--name", request.app_name,
                          "--runtime", "PYTHON:3.12", "--https-only", "true"], 300)
        if created.exit_code or created.timed_out:
            raise ToolFailure("app_creation_failed", "Approved staging app creation failed.", "error")
        configured = runner(
            ["az", "webapp", "config", "appsettings", "set",
             "--resource-group", request.resource_group, "--name", request.app_name,
             "--settings", *request.app_settings],
            180,
        )
        startup = runner(
            ["az", "webapp", "config", "set", "--resource-group", request.resource_group,
             "--name", request.app_name, "--startup-file", request.startup_command],
            180,
        )
        if configured.exit_code or configured.timed_out or startup.exit_code or startup.timed_out:
            runner(["az", "webapp", "stop", "--resource-group", request.resource_group,
                    "--name", request.app_name], 120)
            raise ToolFailure("app_configuration_failed", "Approved staging configuration failed.", "error")
    deployment = ["az", "webapp", "deploy", "--resource-group", request.resource_group,
                  "--name", request.app_name]
    if request.target_kind == "slot":
        deployment += ["--slot", request.slot]
    deployment += ["--type", "zip", "--src-path", str(artifact),
                   "--clean", "true", "--restart", "true"]
    if request.azure_timeout_ms is not None:
        deployment += ["--timeout", str(request.azure_timeout_ms)]
    process_timeout = max(900, ((request.azure_timeout_ms or 840000) // 1000) + 60)
    deployed = runner(deployment, process_timeout)
    if deployed.exit_code or deployed.timed_out:
        stop = ["az", "webapp", "stop", "--resource-group", request.resource_group,
                "--name", request.app_name]
        if request.target_kind == "slot":
            stop += ["--slot", request.slot]
        runner(stop, 120)
        raise ToolFailure("deployment_failed", "Approved staging deployment failed.", "error")

    healthy = False
    for attempt in range(6):
        try:
            healthy = all(probe(url) for url in request.health_urls)
        except OSError:
            healthy = False
        if healthy:
            break
        if attempt < 5:
            wait(5)
    if not healthy:
        stop = ["az", "webapp", "stop", "--resource-group", request.resource_group,
                "--name", request.app_name]
        if request.target_kind == "slot":
            stop += ["--slot", request.slot]
        runner(stop, 120)
        return {"status": "STAGING_VERIFICATION_FAILED", "slot": request.slot,
                "commit": request.commit, "contained": True, "production_changed": False}
    return {"status": "STAGING_VERIFIED", "slot": request.slot, "commit": request.commit,
            "production_changed": False}
