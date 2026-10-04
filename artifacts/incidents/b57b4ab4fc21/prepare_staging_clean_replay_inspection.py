"""Print the exact approval-bound clean replay staging inspection proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash

payload = {
    "action": "start_run_quality_inspect_stop",
    "investigation_id": "b57b4ab4fc21",
    "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "deployed_commit": "70891c7db4e10fb9482c3470cd16d4c6377a9168",
    "deployment_id": "76b6ff0c-fae0-421e-b5ca-2392c0702ff9",
    "artifact_sha256": "cd14dcfbd3b01c113bdeb9e1772b3ecac1b2f3b09bfcaf1999881e470d8fd5a1",
    "quality_input": "backend/tests/fixtures/documents/physics.pdf",
    "quality_input_sha256": "7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5",
    "quality_api": "https://eduforge-ai-staging.azurewebsites.net/api/v1",
    "expected_llm_profile": "ci",
    "max_health_wait_seconds": 300,
    "max_quality_wait_seconds": 300,
    "contain_on_failure": True,
    "production_changed": False,
}
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
