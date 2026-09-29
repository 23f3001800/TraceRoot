"""Bind and execute the approved evidence-valid replay staging deployment."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from traceroot.agents.approval import DeploymentApproval, deployment_action_hash, save_deployment_approval
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload, deploy_verified_staging

ROOT = Path(__file__).resolve().parents[3]
ACTION = "a712b9e6c45eb4b705b87a04c1db01785ea21c339a81c2d298cfabd6973eec60"
request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21replayevidence",
    resource_group="eduforge-rg",
    app_name="eduforge-ai-staging",
    slot="none",
    commit="c1a228127190a395e2124afbb258e8d74857bf78",
    artifact="/tmp/eduforge-c1a2281.zip",
    verification={"status": "FIX_VERIFIED"},
    ci_status="PASSED",
    health_urls=(
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ),
    create_slot=False,
    target_kind="app",
    service_plan="eduforge-plan",
    app_settings=(
        "ENABLE_ORYX_BUILD=true",
        "LLM_PROFILE=ci",
        "PYTHONPATH=/home/site/wwwroot/backend",
        "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
    ),
    startup_command="python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
    azure_timeout_ms=900000,
)
if deployment_action_hash(action_payload(request)) != ACTION:
    raise RuntimeError("deployment action does not match operator approval")
context = SimpleNamespace(
    session_dir=ROOT / ".traceroot-runs" / "eduforgeb57b",
    config={"id": "eduforgeb57b"},
)
now = datetime.now(timezone.utc)
save_deployment_approval(context, DeploymentApproval(
    approval_id=request.approval_id,
    investigation_id=request.investigation_id,
    session_id=context.config["id"],
    approved_action_hash=ACTION,
    approved_by="vikas-explicit-chat-approval",
    approved_at=now.isoformat(),
    expires_at=(now + timedelta(hours=1)).isoformat(),
))
print(json.dumps(deploy_verified_staging(context, request), sort_keys=True))
