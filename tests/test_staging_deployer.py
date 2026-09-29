from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from traceroot.agents.approval import (
    DeploymentApproval,
    deployment_action_hash,
    load_deployment_approval,
    save_deployment_approval,
)
from traceroot.agents.staging_deployer import (
    StagingDeploymentRequest,
    action_payload,
    deploy_verified_staging,
)
from traceroot.contracts import ToolFailure
from traceroot.process import ProcessResult


def request(tmp_path):
    artifact = tmp_path / "release.zip"
    artifact.write_bytes(b"verified release")
    return StagingDeploymentRequest(
        "incident1", "deploy1", "eduforge-rg", "eduforge-ai", "staging",
        "5" * 40, str(artifact), {"status": "FIX_VERIFIED"}, "PASSED",
        ("https://eduforge-ai-staging.azurewebsites.net/healthz",
         "https://eduforge-ai-staging.azurewebsites.net/readyz"), True,
    )


def approve(context, req):
    now = datetime.now(timezone.utc)
    save_deployment_approval(context, DeploymentApproval(
        req.approval_id, req.investigation_id, context.config["id"],
        deployment_action_hash(action_payload(req)), "human", now.isoformat(),
        (now + timedelta(hours=1)).isoformat(),
    ))


def result(code=0):
    return ProcessResult(code, b"", b"", 1, False, False, False)


def test_quality_verification_fields_are_approval_bound():
    payload = {
        "action": "start_and_verify_existing_staging_deployment",
        "investigation_id": "incident1",
        "resource_group": "eduforge-rg",
        "app_name": "eduforge-ai-staging",
        "commit": "5" * 40,
        "artifact_sha256": "a" * 64,
        "azure_deployment_id": "deployment1",
        "health_urls": ["https://example.test/healthz"],
        "quality_input": "physics.pdf",
        "quality_input_sha256": "b" * 64,
        "quality_api": "https://example.test/api/v1",
        "expected_llm_profile": "ci",
        "max_health_wait_seconds": 180,
        "max_quality_wait_seconds": 300,
        "contain_on_failure": True,
        "production_changed": False,
    }
    approved = deployment_action_hash(payload)
    for key in (
        "azure_deployment_id", "quality_input_sha256", "quality_api",
        "expected_llm_profile", "max_health_wait_seconds",
        "max_quality_wait_seconds", "contain_on_failure",
    ):
        changed = {**payload, key: f"changed-{payload[key]}"}
        assert deployment_action_hash(changed) != approved


def test_deploys_only_approved_verified_staging(context, tmp_path):
    req = request(tmp_path); approve(context, req); calls = []
    output = deploy_verified_staging(
        context, req, runner=lambda argv, timeout: calls.append(argv) or result(),
        probe=lambda url: True, wait=lambda seconds: None,
    )
    assert output["status"] == "STAGING_VERIFIED"
    assert calls[0][0:5] == ["az", "webapp", "deployment", "slot", "create"]
    assert "--slot" in calls[1] and "staging" in calls[1]
    assert load_deployment_approval(context, "deploy1").status == "CONSUMED"


def test_failed_healthcheck_stops_isolated_slot(context, tmp_path):
    req = request(tmp_path); approve(context, req); calls = []
    output = deploy_verified_staging(
        context, req, runner=lambda argv, timeout: calls.append(argv) or result(),
        probe=lambda url: False, wait=lambda seconds: None,
    )
    assert output["status"] == "STAGING_VERIFICATION_FAILED"
    assert calls[-1][0:3] == ["az", "webapp", "stop"]
    assert output["production_changed"] is False


def test_rejects_production_and_missing_approval(context, tmp_path):
    req = request(tmp_path)
    with pytest.raises(ToolFailure, match="isolated staging"):
        deploy_verified_staging(context, StagingDeploymentRequest(
            **{**req.__dict__, "slot": "production"}
        ))
    with pytest.raises(ToolFailure) as error:
        deploy_verified_staging(context, req)
    assert error.value.code == "approval_unknown"


def test_creates_separate_staging_app_on_existing_plan(context, tmp_path):
    base = request(tmp_path)
    req = StagingDeploymentRequest(**{
        **base.__dict__, "app_name": "eduforge-ai-staging", "slot": "none",
        "target_kind": "app", "service_plan": "eduforge-plan",
        "app_settings": ("ENABLE_ORYX_BUILD=true", "LLM_PROFILE=ci",
                         "PYTHONPATH=/home/site/wwwroot/backend",
                         "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
        "startup_command": "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
    })
    approve(context, req); calls = []
    output = deploy_verified_staging(
        context, req, runner=lambda argv, timeout: calls.append(argv) or result(),
        probe=lambda url: True, wait=lambda seconds: None,
    )
    assert output["status"] == "STAGING_VERIFIED"
    assert calls[0][0:3] == ["az", "webapp", "create"]
    assert "--plan" in calls[0] and "eduforge-plan" in calls[0]
    assert calls[1][0:5] == ["az", "webapp", "config", "appsettings", "set"]
    assert "--slot" not in calls[3]
    assert calls[4][0:3] == ["az", "webapp", "start"]


def test_failed_deployment_stops_separate_staging_app(context, tmp_path):
    base = request(tmp_path)
    req = StagingDeploymentRequest(**{
        **base.__dict__, "app_name": "eduforge-ai-staging", "slot": "none",
        "target_kind": "app", "service_plan": "eduforge-plan", "create_slot": False,
        "app_settings": ("ENABLE_ORYX_BUILD=true", "LLM_PROFILE=ci",
                         "PYTHONPATH=/home/site/wwwroot/backend",
                         "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
        "startup_command": "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
    })
    approve(context, req); calls = []
    def runner(argv, timeout):
        calls.append(argv)
        return result(1 if argv[0:3] == ["az", "webapp", "deploy"] else 0)
    with pytest.raises(ToolFailure) as error:
        deploy_verified_staging(context, req, runner=runner, wait=lambda seconds: None)
    assert error.value.code == "deployment_failed"
    assert calls[-1][0:3] == ["az", "webapp", "stop"]


def test_passes_approved_azure_deployment_timeout(context, tmp_path):
    base = request(tmp_path)
    req = StagingDeploymentRequest(**{
        **base.__dict__, "app_name": "eduforge-ai-staging", "slot": "none",
        "target_kind": "app", "service_plan": "eduforge-plan", "create_slot": False,
        "app_settings": ("ENABLE_ORYX_BUILD=true", "LLM_PROFILE=ci",
                         "PYTHONPATH=/home/site/wwwroot/backend",
                         "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
        "startup_command": "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
        "azure_timeout_ms": 900000,
    })
    approve(context, req); calls = []
    deploy_verified_staging(
        context, req, runner=lambda argv, timeout: calls.append((argv, timeout)) or result(),
        probe=lambda url: True, wait=lambda seconds: None,
    )
    deploy_call = next(call for call in calls if call[0][0:3] == ["az", "webapp", "deploy"])
    assert deploy_call[0][-2:] == ["--timeout", "900000"]
    assert deploy_call[1] == 960
    assert any(call[0][0:3] == ["az", "webapp", "start"] for call in calls)
