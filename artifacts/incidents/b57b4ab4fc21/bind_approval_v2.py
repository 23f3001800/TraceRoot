"""Bind explicit v2 approval to the existing disposable incident session."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from traceroot.agents.approval import ApprovalRecord, patch_hash, save_approval
from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
patch = (root / "artifacts/incidents/b57b4ab4fc21/proposed-v2.patch").read_text()
expected = "2378784d5a8cb5c2c02a17cffd971923a5b55527b0ad7401dde456770ba35ee9"
if patch_hash(patch) != expected:
    raise RuntimeError("v2 patch hash does not match operator approval")
now = datetime.now(timezone.utc)
record = ApprovalRecord(
    approval_id="b57b4ab4fc21approvalv2",
    investigation_id="b57b4ab4fc21",
    approved_patch_hash=expected,
    repository=context.repository.source,
    session_id=context.config["id"],
    approved_by="vikas-explicit-chat-approval-v2",
    approved_at=now.isoformat(),
    expires_at=(now + timedelta(hours=1)).isoformat(),
)
save_approval(context, record)
print(record.approval_id, record.approved_patch_hash, record.session_id)
