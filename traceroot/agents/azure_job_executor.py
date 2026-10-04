"""Approval-bound Azure Container Apps Job execution for staging remediation."""
from dataclasses import dataclass
import json
import re
from time import sleep
from typing import Callable

from ..contracts import ToolFailure
from ..process import ProcessResult, run_process
from .approval import consume_deployment_approval, deployment_action_hash, load_deployment_approval, valid_now

NAME = re.compile(r"[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")

@dataclass(frozen=True)
class AzureJobRequest:
    investigation_id: str
    approval_id: str
    resource_group: str
    job_name: str
    image_digest: str
    command: tuple[str, ...]
    verification: dict
    timeout_seconds: int = 900

def action_payload(request):
    return {"action":"azure_container_apps_job", "investigation_id":request.investigation_id,
            "resource_group":request.resource_group, "app_name":request.job_name,
            "artifact_sha256":request.image_digest, "verification_status":request.verification.get("status"),
            "max_health_wait_seconds":request.timeout_seconds, "production_changed":False}

def execute_approved_job(context, request, runner: Callable[..., ProcessResult]=run_process, wait=sleep):
    if not NAME.fullmatch(request.resource_group) or not NAME.fullmatch(request.job_name) or not request.job_name.endswith("-staging"):
        raise ToolFailure("target_denied", "Only an explicitly named staging Container Apps Job is allowed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", request.image_digest):
        raise ToolFailure("artifact_denied", "An immutable container image digest is required.")
    if request.verification.get("status") != "FIX_VERIFIED":
        raise ToolFailure("verification_required", "Job execution requires FIX_VERIFIED.")
    if not 30 <= request.timeout_seconds <= 1800 or not request.command or len(request.command) > 32:
        raise ToolFailure("execution_denied", "The bounded job command or timeout is invalid.")
    if any(not isinstance(arg, str) or not arg or len(arg) > 500 for arg in request.command):
        raise ToolFailure("execution_denied", "Job arguments are invalid.")
    try: approval = load_deployment_approval(context, request.approval_id)
    except ValueError: raise ToolFailure("approval_unknown", "No matching execution approval exists.") from None
    expected = deployment_action_hash(action_payload(request))
    if (approval.status != "APPROVED" or approval.consumed_at or not valid_now(approval.expires_at)
            or approval.investigation_id != request.investigation_id
            or approval.session_id != context.config["id"] or approval.approved_action_hash != expected):
        raise ToolFailure("approval_scope_mismatch", "Approval does not cover this exact job execution.")
    consume_deployment_approval(context, request.approval_id)
    started = runner(["az","containerapp","job","start","--resource-group",request.resource_group,
        "--name",request.job_name,"--args",*request.command,"--output","json"], 120)
    if started.exit_code or started.timed_out:
        raise ToolFailure("job_start_failed", "The approved Azure job did not start.", "error")
    try: execution = json.loads(started.stdout)["name"]
    except (ValueError, KeyError, TypeError):
        raise ToolFailure("job_receipt_invalid", "Azure returned no bounded execution identity.", "error") from None
    if not NAME.fullmatch(execution):
        raise ToolFailure("job_receipt_invalid", "Azure returned an invalid execution identity.", "error")
    attempts = max(1, request.timeout_seconds // 10)
    status = "Running"
    for attempt in range(attempts):
        result = runner(["az","containerapp","job","execution","show","--resource-group",request.resource_group,
            "--name",request.job_name,"--job-execution-name",execution,"--output","json"], 60)
        if not result.exit_code and not result.timed_out:
            try: status = json.loads(result.stdout).get("properties",{}).get("status", "Unknown")
            except ValueError: status = "Unknown"
        if status in {"Succeeded", "Failed", "Stopped"}: break
        if attempt + 1 < attempts: wait(10)
    receipt = {"status":"JOB_SUCCEEDED" if status == "Succeeded" else "JOB_FAILED",
               "execution":execution, "azure_status":status, "image_digest":request.image_digest,
               "production_changed":False}
    if status != "Succeeded":
        runner(["az","containerapp","job","stop","--resource-group",request.resource_group,
            "--name",request.job_name,"--job-execution-name",execution], 60)
    return receipt
