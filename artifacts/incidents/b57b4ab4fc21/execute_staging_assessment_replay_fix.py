"""Bind and execute the approved assessment replay staging deployment."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from traceroot.agents.approval import DeploymentApproval, deployment_action_hash, save_deployment_approval
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload, deploy_verified_staging

ROOT = Path(__file__).resolve().parents[3]
ACTION = "2ca4e314cacada649bc5c968a9f67db2afb1babc79022ca130a39130f1579157"
request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21", approval_id="b57b4ab4fc21assessmentreplay",
    resource_group="eduforge-rg", app_name="eduforge-ai-staging", slot="none",
    commit="054a2add3fa0d5a6d87c2c3cadd31282f3346303",
    artifact="/tmp/eduforge-054a2ad.zip", verification={"status": "FIX_VERIFIED"},
    ci_status="PASSED",
    health_urls=("https://eduforge-ai-staging.azurewebsites.net/healthz",
                 "https://eduforge-ai-staging.azurewebsites.net/readyz"),
    create_slot=False, target_kind="app", service_plan="eduforge-plan",
    app_settings=("ENABLE_ORYX_BUILD=true", "LLM_PROFILE=ci",
                  "PYTHONPATH=/home/site/wwwroot/backend",
                  "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
    startup_command="python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
    azure_timeout_ms=900000,
)
if deployment_action_hash(action_payload(request)) != ACTION:
    raise RuntimeError("deployment action does not match operator approval")
context = SimpleNamespace(session_dir=ROOT / ".traceroot-runs" / "eduforgeb57b",
                          config={"id": "eduforgeb57b"})
now = datetime.now(timezone.utc)
save_deployment_approval(context, DeploymentApproval(
    request.approval_id, request.investigation_id, context.config["id"], ACTION,
    "vikas-explicit-chat-approval", now.isoformat(),
    (now + timedelta(hours=1)).isoformat()))
print(json.dumps(deploy_verified_staging(context, request), sort_keys=True))
