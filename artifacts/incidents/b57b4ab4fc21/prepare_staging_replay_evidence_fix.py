"""Print the approval-bound evidence-valid replay staging deployment."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload

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
payload = action_payload(request)
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
