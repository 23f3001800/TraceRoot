"""Print the exact approval-bound clean replay staging proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload

request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21cleanreplay20261003",
    resource_group="eduforge-rg",
    app_name="eduforge-ai-staging",
    slot="none",
    commit="70891c7db4e10fb9482c3470cd16d4c6377a9168",
    artifact="/tmp/eduforge-70891c7.zip",
    verification={"status": "FIX_VERIFIED"},
    ci_status="PASSED",
    health_urls=(
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ),
    create_slot=True,
    target_kind="app",
    service_plan="eduforge-plan",
    app_settings=(
        "ENABLE_ORYX_BUILD=true",
        "LLM_PROFILE=ci",
        "PYTHONPATH=/home/site/wwwroot/backend",
        "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
    ),
    startup_command=(
        "python -m uvicorn api.main:app --host 0.0.0.0 "
        "--port 8000 --app-dir backend"
    ),
    azure_timeout_ms=900000,
)
payload = action_payload(request)
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
