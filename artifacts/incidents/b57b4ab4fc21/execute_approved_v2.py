"""Execute only the approval-bound v2 patch in disposable Docker."""
import json
from pathlib import Path

from traceroot.agents.sandbox_executor import ExecutionRequest, execute_approved_patch
from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
patch = (root / "artifacts/incidents/b57b4ab4fc21/proposed-v2.patch").read_text()
request = ExecutionRequest(
    approval_id="b57b4ab4fc21approvalv2",
    repository=context.repository.source,
    patch=patch,
    plan={"scope": "case-insensitive explicit grade label matching"},
)
print(json.dumps(execute_approved_patch(context, request), sort_keys=True))
