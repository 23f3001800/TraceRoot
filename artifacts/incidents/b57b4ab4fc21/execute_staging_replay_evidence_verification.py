"""Execute the approved quality check for the evidence-valid staging deployment."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

import httpx

from traceroot.agents.approval import (
    DeploymentApproval, consume_deployment_approval, deployment_action_hash,
    load_deployment_approval, save_deployment_approval, valid_now,
)
from traceroot.process import run_process

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path("/home/vikas/EduForge-AI")
APPROVAL_ID = "b57b4ab4fc21evidenceverify"
ACTION = "a2079ecc41cf850ac9b3c94fc7ca28febd1eb3da3c7e10d8480c1ab738eb78b6"
payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21", "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "c1a228127190a395e2124afbb258e8d74857bf78",
    "artifact_sha256": "975c370c634916cb1fdc55a78e38ce7ee2e891f605ce0ca20de3ed02fbeafadd",
    "azure_deployment_id": "ca052510-fb26-40e1-8c76-9cead46c0f0e",
    "health_urls": ["https://eduforge-ai-staging.azurewebsites.net/healthz",
                    "https://eduforge-ai-staging.azurewebsites.net/readyz"],
    "quality_input": "backend/tests/fixtures/documents/physics.pdf",
    "quality_input_sha256": "7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5",
    "quality_api": "https://eduforge-ai-staging.azurewebsites.net/api/v1",
    "expected_llm_profile": "ci", "max_health_wait_seconds": 180,
    "max_quality_wait_seconds": 300, "contain_on_failure": True,
    "production_changed": False,
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(*args, timeout=120):
    result = run_process(["az", *args], timeout)
    if result.exit_code or result.timed_out:
        raise RuntimeError("Azure staging command failed")


def stop():
    run_process(["az", "webapp", "stop", "--resource-group", "eduforge-rg",
                 "--name", "eduforge-ai-staging"], 120)


def execute():
    if deployment_action_hash(payload) != ACTION:
        raise RuntimeError("verification action does not match approval")
    fixture = APP_ROOT / payload["quality_input"]
    if sha256("/tmp/eduforge-c1a2281.zip") != payload["artifact_sha256"] or sha256(fixture) != payload["quality_input_sha256"]:
        raise RuntimeError("approved input hash mismatch")
    context = SimpleNamespace(session_dir=ROOT / ".traceroot-runs" / "eduforgeb57b",
                              config={"id": "eduforgeb57b"})
    now = datetime.now(timezone.utc)
    save_deployment_approval(context, DeploymentApproval(
        APPROVAL_ID, payload["investigation_id"], context.config["id"], ACTION,
        "vikas-explicit-chat-approval", now.isoformat(),
        (now + timedelta(hours=1)).isoformat()))
    approval = load_deployment_approval(context, APPROVAL_ID)
    if approval.approved_action_hash != ACTION or not valid_now(approval.expires_at):
        raise RuntimeError("approval scope mismatch")
    consume_deployment_approval(context, APPROVAL_ID)
    command("webapp", "start", "--resource-group", "eduforge-rg", "--name", "eduforge-ai-staging")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        deadline = monotonic() + payload["max_health_wait_seconds"]
        while monotonic() < deadline:
            try:
                health = client.get(payload["health_urls"][0])
                ready = client.get(payload["health_urls"][1])
                if health.status_code == ready.status_code == 200 and ready.json().get("llm_profile") == "ci":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            sleep(5)
        else:
            raise RuntimeError("staging health verification failed")
        with fixture.open("rb") as stream:
            uploaded = client.post(payload["quality_api"] + "/documents",
                                   files={"file": (fixture.name, stream, "application/pdf")})
        uploaded.raise_for_status()
        document = uploaded.json()
        if document.get("sha256") != payload["quality_input_sha256"]:
            raise RuntimeError("uploaded document hash mismatch")
        created = client.post(payload["quality_api"] + "/jobs",
                              json={"document_id": document["document_id"]})
        created.raise_for_status()
        job_id = created.json()["job_id"]
        deadline = monotonic() + payload["max_quality_wait_seconds"]
        while monotonic() < deadline:
            response = client.get(payload["quality_api"] + "/jobs/" + job_id)
            response.raise_for_status()
            job = response.json()
            if job.get("status") in {"succeeded", "succeeded_partial", "failed", "cancelled"}:
                break
            sleep(2)
        else:
            raise RuntimeError("quality job exceeded approved timeout")
        if job.get("status") != "succeeded":
            raise RuntimeError("quality job did not recover: " + json.dumps(job, sort_keys=True))
        return {"status": "RECOVERY_VERIFIED", "deployment_id": payload["azure_deployment_id"],
                "commit": payload["commit"], "healthz": health.json(), "readyz": ready.json(),
                "quality_job": job, "production_changed": False}


try:
    output = execute()
except Exception as exc:
    stop()
    output = {"status": "RECOVERY_NOT_VERIFIED", "error": f"{type(exc).__name__}: {exc}",
              "contained": True, "production_changed": False}
print(json.dumps(output, indent=2, sort_keys=True))
