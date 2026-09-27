"""Print the approval-bound target commit proposal without changing Git state."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from traceroot.agents.approval import commit_action_hash, patch_hash

REPOSITORY = Path("/tmp/eduforge-recovery-b57b4ab4fc21").resolve()
BRANCH = "traceroot/b57b4ab4fc21-grade-band-recovery"
COMMIT_MESSAGE = "Handle low-confidence grade bands safely"
VERIFICATION = {"status": "FIX_VERIFIED"}

patch = subprocess.run(
    ["git", "-C", str(REPOSITORY), "diff", "--cached", "--binary", "--"],
    check=True,
    capture_output=True,
    text=True,
).stdout

print(
    json.dumps(
        {
            "repository": str(REPOSITORY),
            "branch": BRANCH,
            "commit_message": COMMIT_MESSAGE,
            "verification_status": VERIFICATION["status"],
            "patch_sha256": patch_hash(patch),
            "action_sha256": commit_action_hash(
                str(REPOSITORY), patch, BRANCH, COMMIT_MESSAGE, VERIFICATION
            ),
        },
        indent=2,
        sort_keys=True,
    )
)
