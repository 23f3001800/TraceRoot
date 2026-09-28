"""Print the exact approval-bound separate staging-app proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload

request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21stagingapp",
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
    create_slot=True,
    target_kind="app",
    service_plan="eduforge-plan",
    app_settings=("LLM_PROFILE=ci", "SCM_DO_BUILD_DURING_DEPLOYMENT=true"),
    startup_command="python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend",
)
payload = action_payload(request)
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
