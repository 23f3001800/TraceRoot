"""Print the approval-bound replay-cassette staging redeployment proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload

request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21replayfix",
    resource_group="eduforge-rg",
    app_name="eduforge-ai-staging",
    slot="none",
    commit="b2bfbb7fd461b9c8e1cf4b8e8db18e9474e63a10",
    artifact="/tmp/eduforge-b2bfbb7.zip",
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
payload = action_payload(request)
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
