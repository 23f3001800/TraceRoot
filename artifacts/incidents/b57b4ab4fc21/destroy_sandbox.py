"""Destroy resources owned by the completed incident session."""
import json
from pathlib import Path

from traceroot.agents.sandbox_executor import destroy_sandbox
from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
print(json.dumps(destroy_sandbox(context), sort_keys=True))
