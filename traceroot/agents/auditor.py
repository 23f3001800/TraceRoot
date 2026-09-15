"""Evidence-only Auditor boundary for read-only investigations."""
from __future__ import annotations

import json
from typing import Any

from .schemas import AUDIT_SCHEMA

AUDITOR_PROMPT = """You are the Evidence Auditor in a read-only incident investigation. You have no tools and cannot investigate. Inspect only the supplied incident, candidate hypotheses, and cited tool observations. Check whether each claimed cause correlates with the reproduced incident, whether citations support it, and whether observations contradict it. Return SUPPORTED only for a candidate root cause backed by concrete evidence. For INSUFFICIENT or CONTRADICTED, state unsupported claims, the evidence missing, and the evidence required next. Describe needed evidence, never a tool to call. Never select tools, edit hypotheses, invent evidence, or agree without verification."""


def audit_request(state: dict[str, Any]) -> list[dict[str, str]]:
    """Build the Auditor's evidence-only input; tools and transcripts stay hidden."""
    return [{"role": "user", "text": json.dumps({
        "incident": state["incident"], "reproduction": state["reproduction"],
        "observations": state["observations"], "hypotheses": state["hypotheses"],
        "evidence": state["evidence"],
        "instruction": "Audit the candidate root-cause claims and their cited evidence. You have no tools."})}]


__all__ = ["AUDITOR_PROMPT", "AUDIT_SCHEMA", "audit_request"]
