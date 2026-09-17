import pytest
from traceroot.agents.pr_draft import DraftPRRequest, prepare_draft_pr
from traceroot.contracts import ToolFailure

def request(status="FIX_VERIFIED"):
    return DraftPRRequest("bug-003-e2e", "Retries create duplicate orders.",
        "Idempotency key was not reused.", ["Reproduction returned IDs 1 and 2."],
        "Return the existing order for a repeated key.", ["app/services.py"],
        {"status": status}, "traceroot/bug-003-idempotency", "a" * 40, [])

def test_prepares_non_publishing_draft():
    result = prepare_draft_pr(request())
    assert result["status"] == "DRAFT_PR_READY"
    assert result["published"] is False
    assert "FIX_VERIFIED" in result["body"]

def test_rejects_unverified_draft():
    with pytest.raises(ToolFailure) as error:
        prepare_draft_pr(request("REGRESSION_INTRODUCED"))
    assert error.value.code == "verification_required"
