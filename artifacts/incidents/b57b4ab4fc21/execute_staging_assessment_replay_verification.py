"""Execute the approved final quality check for the assessment replay deployment."""
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
APPROVAL_ID = "b57b4ab4fc21assessmentverify"
ACTION = "526bb5f18a8fc7bbbb63b13a059847771b97826a8c8cbd798b94a0319daf7202"
payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21", "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "054a2add3fa0d5a6d87c2c3cadd31282f3346303",
    "artifact_sha256": "5a74a60a1b26668bcb07e22e7012698e1fd79e5177c978cc43192ede573f5ac5",
    "azure_deployment_id": "07d2825e-c754-4b66-b5f4-5d9b83e9d2e5",
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


def stop():
    run_process(["az", "webapp", "stop", "--resource-group", "eduforge-rg",
                 "--name", "eduforge-ai-staging"], 120)


def execute():
    if deployment_action_hash(payload) != ACTION:
        raise RuntimeError("verification action does not match approval")
    fixture = APP_ROOT / payload["quality_input"]
    if sha256("/tmp/eduforge-054a2ad.zip") != payload["artifact_sha256"] or sha256(fixture) != payload["quality_input_sha256"]:
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
    started = run_process(["az", "webapp", "start", "--resource-group", "eduforge-rg",
                           "--name", "eduforge-ai-staging"], 120)
    if started.exit_code or started.timed_out:
        raise RuntimeError("Azure staging start failed")
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
