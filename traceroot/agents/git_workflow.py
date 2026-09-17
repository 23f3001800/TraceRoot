"""Post-verification local Git workflow; publishing remains separate."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from ..contracts import ToolFailure
from ..process import run_process
from .patch_policy import validate_patch

_BRANCH = re.compile(r"traceroot/[a-z0-9][a-z0-9-]{2,63}$")

@dataclass(frozen=True)
class VerifiedBranchRequest:
    investigation_id: str
    repository: str
    patch: str
    verification: dict
    branch: str
    commit_message: str

def _git(root: Path, args: list[str], *, input_bytes: bytes | None = None) -> str:
    result = run_process(["git", "-C", str(root), *args], 30, input_bytes, 8192)
    if result.timed_out:
        raise ToolFailure("git_timeout", "Local Git operation timed out.", "timeout")
    if result.exit_code:
        raise ToolFailure("git_operation_failed", "Local Git operation was rejected.", "error")
    return result.stdout.decode("utf-8", errors="replace").strip()

def _validate(request: VerifiedBranchRequest) -> tuple[Path, list[str]]:
    if request.verification.get("status") != "FIX_VERIFIED":
        raise ToolFailure("verification_required", "Branch creation requires FIX_VERIFIED.")
    if not _BRANCH.fullmatch(request.branch):
        raise ToolFailure("branch_denied", "Branch must be a bounded traceroot/ branch name.")
    words = request.commit_message.split()
    if not 3 <= len(words) <= 7 or len(request.commit_message) > 72:
        raise ToolFailure("commit_message_denied", "Commit message must contain three to seven words.")
    root = Path(request.repository).resolve()
    if not (root / ".git").exists():
        raise ToolFailure("repository_denied", "A local Git repository is required.")
    files = validate_patch(request.patch)
    if _git(root, ["status", "--porcelain"]):
        raise ToolFailure("repository_dirty", "Repository must be clean before branch creation.")
    return root, files

def create_verified_branch_commit(request: VerifiedBranchRequest) -> dict:
    """Create one local commit after deterministic verification. Never pushes."""
    root, files = _validate(request)
    source_branch = _git(root, ["branch", "--show-current"])
    if not source_branch:
        raise ToolFailure("branch_denied", "Detached HEAD cannot create a verified branch.")
    exists = run_process(["git", "-C", str(root), "show-ref", "--verify", "--quiet", f"refs/heads/{request.branch}"], 15)
    if exists.exit_code == 0:
        raise ToolFailure("branch_exists", "Verified branch already exists.")
    _git(root, ["switch", "-c", request.branch])
    _git(root, ["apply", "--check", "--whitespace=error-all", "-"], input_bytes=request.patch.encode())
    _git(root, ["apply", "--whitespace=error-all", "-"], input_bytes=request.patch.encode())
    _git(root, ["diff", "--check"])
    _git(root, ["add", "--", *files])
    _git(root, ["commit", "-m", request.commit_message])
    commit = _git(root, ["rev-parse", "HEAD"])
    return {"status": "BRANCH_COMMITTED", "investigation_id": request.investigation_id,
            "branch": request.branch, "commit": commit, "source_branch": source_branch,
            "files": files, "published": False}
