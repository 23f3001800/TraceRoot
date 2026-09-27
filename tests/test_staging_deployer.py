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
