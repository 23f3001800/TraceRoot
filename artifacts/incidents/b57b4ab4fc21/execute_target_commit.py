"""Consume the explicit approval and commit the verified EduForge patch locally."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from traceroot.agents.approval import (
    TargetCommitApproval,
    commit_action_hash,
    consume_target_commit_approval,
    save_target_commit_approval,
)

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = Path("/tmp/eduforge-recovery-b57b4ab4fc21").resolve()
BRANCH = "traceroot/b57b4ab4fc21-grade-band-recovery"
MESSAGE = "Handle low-confidence grade bands safely"
ACTION = "a04f8c006bfcb6e0820d79c92ec9a20dedfaa095fb75087a21482104b0a546da"
APPROVAL_ID = "b57b4ab4fc21targetcommit"
SESSION_ID = "eduforgeb57b"
FILE = "backend/stages/s2_classification/stage.py"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPOSITORY), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if git("branch", "--show-current") != BRANCH:
    raise RuntimeError("unexpected recovery branch")
if git("status", "--porcelain") != f"M  {FILE}":
    raise RuntimeError("target worktree is not the exact staged proposal")
git("diff", "--cached", "--check")
patch = git("diff", "--cached", "--binary", "--") + "\n"
verification = {"status": "FIX_VERIFIED"}
if commit_action_hash(str(REPOSITORY), patch, BRANCH, MESSAGE, verification) != ACTION:
    raise RuntimeError("target action does not match operator approval")

context = SimpleNamespace(
    session_dir=ROOT / ".traceroot-runs" / SESSION_ID,
    config={"id": SESSION_ID},
)
now = datetime.now(timezone.utc)
save_target_commit_approval(
    context,
    TargetCommitApproval(
        approval_id=APPROVAL_ID,
        investigation_id="b57b4ab4fc21",
        target_repository=str(REPOSITORY),
        session_id=SESSION_ID,
        approved_action_hash=ACTION,
        approved_by="vikas-explicit-chat-approval",
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(hours=1)).isoformat(),
    ),
)
git("commit", "-m", MESSAGE)
commit = git("rev-parse", "HEAD")
consume_target_commit_approval(context, APPROVAL_ID)
print(json.dumps({"status": "BRANCH_COMMITTED", "branch": BRANCH, "commit": commit, "published": False}))
