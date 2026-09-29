"""Print the exact start and quality check for the evidence-valid deployment."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash

payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21",
    "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "c1a228127190a395e2124afbb258e8d74857bf78",
    "artifact_sha256": "975c370c634916cb1fdc55a78e38ce7ee2e891f605ce0ca20de3ed02fbeafadd",
    "azure_deployment_id": "ca052510-fb26-40e1-8c76-9cead46c0f0e",
    "health_urls": [
        "https://eduforge-ai-staging.azurewebsites.net/healthz",
        "https://eduforge-ai-staging.azurewebsites.net/readyz",
    ],
    "quality_input": "backend/tests/fixtures/documents/physics.pdf",
    "quality_input_sha256": "7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5",
    "quality_api": "https://eduforge-ai-staging.azurewebsites.net/api/v1",
    "expected_llm_profile": "ci",
    "max_health_wait_seconds": 180,
    "max_quality_wait_seconds": 300,
    "contain_on_failure": True,
    "production_changed": False,
}
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
