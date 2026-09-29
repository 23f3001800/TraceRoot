"""Print the exact approval-bound start and quality-verification proposal."""
from __future__ import annotations

import json

from traceroot.agents.approval import deployment_action_hash

payload = {
    "action": "start_and_verify_existing_staging_deployment",
    "investigation_id": "b57b4ab4fc21",
    "resource_group": "eduforge-rg",
    "app_name": "eduforge-ai-staging",
    "commit": "b2bfbb7fd461b9c8e1cf4b8e8db18e9474e63a10",
    "artifact_sha256": "b021d4b938e5410ac86b705b8e4581b3af9c5f9a74aec1c96baee2197ea70388",
    "azure_deployment_id": "17ea5f02-2726-44c2-b643-50b2c4743581",
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
