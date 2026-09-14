from __future__ import annotations

from ..contracts import ToolFailure, ToolResult, bounded_int, tool
from ..process import run_process
from ..repository import public_file


def _git(context, args: list[str]):
    result = run_process(["git", "-C", context.repository.source, *args], 10, limit=32768)
    if result.timed_out:
        raise ToolFailure("git_timeout", "Git inspection timed out.", "timeout")
    if result.exit_code != 0:
        raise ToolFailure("git_unavailable", "Registered repository has no readable Git history.", "unavailable")
    return result.stdout.decode("utf-8", errors="replace")

@tool
def inspect_git(context, repository: str, operation: str, limit: int = 10) -> ToolResult:
    context.repository.validate(repository)
    bounded_int(limit, 1, 20, "limit")
    if operation == "history":
        lines = _git(context, ["log", f"-n{limit}", "--format=%H%x1f%h%x1f%s%x1f%aI"])
        entries = [{"commit": a, "short_commit": b, "subject": c[:500], "timestamp": d} for line in lines.splitlines() if (parts := line.split("\x1f")) and len(parts) == 4 for a, b, c, d in [parts]]
    elif operation == "changed_files":
        lines = _git(context, ["diff", "--name-status", "HEAD~1", "HEAD"])
        entries = [{"status": parts[0], "file": parts[-1]} for line in lines.splitlines() if (parts := line.split("\t")) and len(parts) >= 2 and public_file(parts[-1])][:limit]
    elif operation == "dependency_changes":
        lines = _git(context, ["diff", "--unified=3", "HEAD~1", "HEAD", "--", "requirements.txt", "pyproject.toml", "setup.cfg"])
        entries = [{"line": line[:1000]} for line in lines.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))][:limit]
    else:
        raise ToolFailure("invalid_operation", "operation must be history, changed_files, or dependency_changes.")
    return ToolResult("ok", {"operation": operation, "entries": entries, "truncated": len(entries) >= limit}, metadata={"snapshot_id": context.repository.snapshot_id})
