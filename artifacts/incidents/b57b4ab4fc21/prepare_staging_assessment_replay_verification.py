"""Print the exact quality check for the assessment-corrected deployment."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash

payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21", "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "054a2add3fa0d5a6d87c2c3cadd31282f3346303",
    "artifact_sha256": "5a74a60a1b26668bcb07e22e7012698e1fd79e5177c978cc43192ede573f5ac5",
    "azure_deployment_id": "07d2825e-c754-4b66-b5f4-5d9b83e9d2e5",
    "health_urls": ["https://eduforge-ai-staging.azurewebsites.net/healthz",
                    "https://eduforge-ai-staging.azurewebsites.net/readyz"],
    "quality_input": "backend/tests/fixtures/documents/physics.pdf",
    "quality_input_sha256": "7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5",
    "quality_api": "https://eduforge-ai-staging.azurewebsites.net/api/v1",
    "expected_llm_profile": "ci", "max_health_wait_seconds": 180,
    "max_quality_wait_seconds": 300, "contain_on_failure": True,
    "production_changed": False,
}
print(json.dumps({**payload, "action_sha256": deployment_action_hash(payload)}, indent=2, sort_keys=True))
