"""Bind and execute the approved bounded-timeout staging retry."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from traceroot.agents.approval import DeploymentApproval, deployment_action_hash, save_deployment_approval
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload, deploy_verified_staging

ROOT = Path(__file__).resolve().parents[3]
ACTION = "74404a860e0c594f859955498bd96eefb20e33a3b28970c40ba6c1ac4953c714"
request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21stagingtimeout",
    resource_group="eduforge-rg",
    app_name="eduforge-ai-staging",
    slot="none",
    commit="530cf31ef774af989e29db1d209372173c86f8bb",
    artifact="/tmp/eduforge-530cf31.zip",
    verification={"status": "FIX_VERIFIED"},
    ci_status="PASSED",
    health_urls=(
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ),
    create_slot=False,
    target_kind="app",
    service_plan="eduforge-plan",
    app_settings=("LLM_PROFILE=ci", "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
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
