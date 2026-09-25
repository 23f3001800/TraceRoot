"""Execute only the approval-bound incident patch in disposable Docker."""
import json
from pathlib import Path

from traceroot.agents.sandbox_executor import ExecutionRequest, execute_approved_patch
from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
patch = (root / "artifacts/incidents/b57b4ab4fc21/proposed.patch").read_text()
request = ExecutionRequest(
    approval_id="b57b4ab4fc21approval",
    repository=context.repository.source,
    patch=patch,
    plan={"scope": "classification checkpoint low-confidence grade handling"},
)
print(json.dumps(execute_approved_patch(context, request), sort_keys=True))
