"""Draft-PR report preparation; this module never publishes."""
from __future__ import annotations
from dataclasses import dataclass
import re
from ..contracts import ToolFailure

_BRANCH = re.compile(r"traceroot/[a-z0-9][a-z0-9-]{2,63}$")
_SECRET = re.compile(r"(?i)(api[_-]?key|password|token)\s*[:=]\s*\S+")

@dataclass(frozen=True)
class DraftPRRequest:
    investigation_id: str
    incident: str
    root_cause: str
    evidence: list[str]
    remediation: str
    files: list[str]
    verification: dict
    branch: str
    commit: str
    limitations: list[str]

def _text(value: str, name: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or _SECRET.search(value):
        raise ToolFailure("draft_input_denied", f"{name} is invalid or contains a secret.")
    return value.strip()

def prepare_draft_pr(request: DraftPRRequest) -> dict:
    if request.verification.get("status") != "FIX_VERIFIED":
        raise ToolFailure("verification_required", "Draft PR preparation requires FIX_VERIFIED.")
    if not _BRANCH.fullmatch(request.branch):
        raise ToolFailure("branch_denied", "Draft PR requires a verified traceroot/ branch.")
    if not re.fullmatch(r"[0-9a-f]{7,64}", request.commit):
        raise ToolFailure("commit_denied", "Draft PR requires a commit SHA.")
    incident = _text(request.incident, "incident")
    cause = _text(request.root_cause, "root cause")
    remediation = _text(request.remediation, "remediation")
    evidence = [_text(item, "evidence", 500) for item in request.evidence[:12]]
    limitations = [_text(item, "limitation", 300) for item in request.limitations[:12]]
    if not evidence or not request.files or len(request.files) > 10:
        raise ToolFailure("draft_input_denied", "Draft PR requires bounded files and evidence.")
    files = [_text(item, "file", 240) for item in request.files]
    body = "\n".join([
        "## Incident", incident, "", "## Root cause", cause, "", "## Evidence",
        *[f"- {item}" for item in evidence], "", "## Remediation", remediation,
        "", "## Files changed", *[f"- {item}" for item in files],
        "", "## Verification", "- FIX_VERIFIED",
        f"- Branch: {request.branch}", f"- Commit: {request.commit}",
        "", "## Limitations", *( [f"- {item}" for item in limitations] if limitations else ["- None recorded."] ),
        "", f"TraceRoot investigation: {request.investigation_id}",
    ])
    return {"status": "DRAFT_PR_READY", "title": f"Fix: {cause[:72]}",
            "body": body, "branch": request.branch, "commit": request.commit,
            "published": False}
