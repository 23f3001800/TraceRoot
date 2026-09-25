"""Run deterministic post-patch verification for incident b57b4ab4fc21."""
import json
from pathlib import Path

from traceroot.agents.verifier import verify_remediation
from traceroot.context import Context
from traceroot.contracts import ToolFailure

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
try:
    result = verify_remediation(
        context,
        reproduction_args=["evaluation/test_grade_band_quality.py"],
        focused_args=["backend/tests/unit/test_knowledge_core.py"],
        regression_args=["backend/tests/unit"],
        timeout=120,
    )
except ToolFailure as failure:
    result = {"status": "VERIFICATION_TOOL_FAILURE",
              "error": {"code": failure.code, "message": failure.message}}
print(json.dumps(result, indent=2, sort_keys=True))
