"""Print the exact approval-bound Azure staging deployment proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash
from traceroot.agents.staging_deployer import StagingDeploymentRequest, action_payload

request = StagingDeploymentRequest(
    investigation_id="b57b4ab4fc21",
    approval_id="b57b4ab4fc21staging",
    resource_group="eduforge-rg",
    app_name="eduforge-ai",
    slot="staging",
    commit="530cf31ef774af989e29db1d209372173c86f8bb",
    artifact="/tmp/eduforge-530cf31.zip",
    verification={"status": "FIX_VERIFIED"},
    ci_status="PASSED",
    health_urls=(
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ),
    create_slot=True,
)
payload = action_payload(request)
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
