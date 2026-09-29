"""Execute the approved start, health check, and replay-quality verification."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

import httpx

from traceroot.agents.approval import (
    DeploymentApproval,
    consume_deployment_approval,
    deployment_action_hash,
    load_deployment_approval,
    save_deployment_approval,
    valid_now,
)
from traceroot.process import run_process

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path("/tmp/eduforge-replay-fix")
APPROVAL_ID = "b57b4ab4fc21replayverify"
ACTION = "2e3337dbb5297bba4a956dc689e07e0454f7022a6cd6ea542f0d652ccc136f30"
payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21",
    "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "b2bfbb7fd461b9c8e1cf4b8e8db18e9474e63a10",
    "artifact_sha256": "b021d4b938e5410ac86b705b8e4581b3af9c5f9a74aec1c96baee2197ea70388",
    "azure_deployment_id": "17ea5f02-2726-44c2-b643-50b2c4743581",
    "health_urls": [
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ],
    "quality_input": "backend/tests/fixtures/documents/physics.pdf",
    "quality_input_sha256": "7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5",
    "quality_api": "https://eduforge-ai-staging.azurewebsites.net/api/v1",
    "expected_llm_profile": "ci",
    "max_health_wait_seconds": 180,
    "max_quality_wait_seconds": 300,
    "contain_on_failure": True,
    "production_changed": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def azure(*args: str, timeout: int = 120):
    result = run_process(["az", *args], timeout)
    if result.exit_code or result.timed_out:
        raise RuntimeError(f"Azure command failed: {' '.join(args[:3])}")
    return result


def stop_staging() -> None:
    run_process([
        "az", "webapp", "stop", "--resource-group", payload["resource_group"],
        "--name", payload["app_name"],
    ], 120)


def main() -> dict:
    if deployment_action_hash(payload) != ACTION:
        raise RuntimeError("verification action does not match operator approval")
    artifact = Path("/tmp/eduforge-b2bfbb7.zip")
    fixture = APP_ROOT / payload["quality_input"]
    if sha256(artifact) != payload["artifact_sha256"]:
        raise RuntimeError("artifact hash mismatch")
    if sha256(fixture) != payload["quality_input_sha256"]:
        raise RuntimeError("quality input hash mismatch")

    context = SimpleNamespace(
        session_dir=ROOT / ".traceroot-runs" / "eduforgeb57b",
        config={"id": "eduforgeb57b"},
    )
    now = datetime.now(timezone.utc)
    save_deployment_approval(context, DeploymentApproval(
        approval_id=APPROVAL_ID,
        investigation_id=payload["investigation_id"],
        session_id=context.config["id"],
        approved_action_hash=ACTION,
        approved_by="vikas-explicit-chat-approval",
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(hours=1)).isoformat(),
    ))
    approval = load_deployment_approval(context, APPROVAL_ID)
    if approval.approved_action_hash != ACTION or not valid_now(approval.expires_at):
        raise RuntimeError("approval scope mismatch")
    consume_deployment_approval(context, APPROVAL_ID)

    azure("webapp", "start", "--resource-group", payload["resource_group"],
          "--name", payload["app_name"])
    base = payload["quality_api"]
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        deadline = monotonic() + payload["max_health_wait_seconds"]
        health = ready = None
        while monotonic() < deadline:
            try:
                health_response = client.get(payload["health_urls"][0])
                ready_response = client.get(payload["health_urls"][1])
                if health_response.status_code == ready_response.status_code == 200:
                    health = health_response.json()
                    ready = ready_response.json()
                    if ready.get("llm_profile") == payload["expected_llm_profile"]:
                        break
            except (httpx.HTTPError, ValueError):
                pass
            sleep(5)
        else:
            raise RuntimeError("staging health or replay profile verification failed")

        with fixture.open("rb") as stream:
            uploaded = client.post(
                f"{base}/documents",
                files={"file": (fixture.name, stream, "application/pdf")},
            )
        uploaded.raise_for_status()
        document = uploaded.json()
        if document.get("sha256") != payload["quality_input_sha256"]:
            raise RuntimeError("staging document hash mismatch")

        created = client.post(f"{base}/jobs", json={"document_id": document["document_id"]})
        created.raise_for_status()
        job_id = created.json()["job_id"]
        deadline = monotonic() + payload["max_quality_wait_seconds"]
        job = None
        while monotonic() < deadline:
            response = client.get(f"{base}/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job.get("status") in {"succeeded", "succeeded_partial", "failed", "cancelled"}:
                break
            sleep(2)
        else:
            raise RuntimeError("quality job exceeded approved timeout")
        if job is None or job.get("status") != "succeeded":
            raise RuntimeError(f"quality job did not recover: {json.dumps(job, sort_keys=True)}")
        return {
            "status": "RECOVERY_VERIFIED",
            "deployment_id": payload["azure_deployment_id"],
            "commit": payload["commit"],
            "healthz": health,
            "readyz": ready,
            "quality_job": job,
            "production_changed": False,
        }


try:
    output = main()
except Exception as exc:
    stop_staging()
    output = {
        "status": "RECOVERY_NOT_VERIFIED",
        "error": f"{type(exc).__name__}: {exc}",
        "contained": True,
        "production_changed": False,
    }
print(json.dumps(output, indent=2, sort_keys=True))
