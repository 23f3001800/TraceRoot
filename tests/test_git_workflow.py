import subprocess
from pathlib import Path
import pytest
from traceroot.agents.git_workflow import VerifiedBranchRequest, create_verified_branch_commit
from traceroot.contracts import ToolFailure

PATCH = """diff --git a/app/value.py b/app/value.py
--- a/app/value.py
+++ b/app/value.py
@@ -1 +1 @@
-old
+new
"""

def command(root, *args):
    return subprocess.run(args, cwd=root, check=True, capture_output=True, text=True)

def repository(tmp_path):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "value.py").write_text("old\n")
    command(root, "git", "init", "-q")
    command(root, "git", "config", "user.email", "trace@example.test")
    command(root, "git", "config", "user.name", "TraceRoot Test")
    command(root, "git", "add", "app/value.py")
    command(root, "git", "commit", "-qm", "Create initial verification fixture")
    return root

def request(root, status="FIX_VERIFIED"):
    return VerifiedBranchRequest("bug-003-e2e", str(root), PATCH, {"status": status},
                                 "traceroot/bug-003-idempotency", "Fix repeated order idempotency handling")

def test_creates_local_verified_branch_commit(tmp_path):
    root = repository(tmp_path)
    result = create_verified_branch_commit(request(root))
    assert result["status"] == "BRANCH_COMMITTED"
    assert result["branch"] == "traceroot/bug-003-idempotency"
    assert result["published"] is False
    assert (root / "app" / "value.py").read_text() == "new\n"
    assert command(root, "git", "status", "--porcelain").stdout == ""

def test_requires_deterministic_verification(tmp_path):
    with pytest.raises(ToolFailure) as error:
        create_verified_branch_commit(request(repository(tmp_path), "REPRODUCTION_STILL_FAILS"))
    assert error.value.code == "verification_required"
