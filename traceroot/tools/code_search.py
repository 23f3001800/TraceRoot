from pathlib import PurePosixPath
from ..contracts import ToolFailure, ToolResult, bounded_int, tool
from ..repository import relative_path

@tool
def search_code(context, repository: str, query: str, path_scope: str = ".",
                result_limit: int = 20) -> ToolResult:
    context.repository.validate(repository)
    if not isinstance(query, str) or not 1 <= len(query) <= 200:
        raise ToolFailure("invalid_query", "Use a literal query of 1 to 200 characters.")
    bounded_int(result_limit, 1, 100, "result_limit")
    scope = relative_path(path_scope, allow_dot=True)
    paths = [p for p in context.repository.manifest
             if scope == "." or p == scope or p.startswith(scope + "/")]
    if not paths:
        raise ToolFailure("scope_not_found", "No public files exist in that scope.")
    results, used, truncated = [], 0, False
    for path in sorted(paths):
        lines = context.repository.read(path).splitlines()
        for index, line in enumerate(lines):
            if query not in line:
                continue
            match = {"file": path, "line": index + 1, "text": line[:1000],
                     "context": [{"line": n + 1, "text": lines[n][:1000]}
                                 for n in range(max(0, index - 1), min(len(lines), index + 2))],
                     "text_truncated": len(line) > 1000}
            used += sum(len(c["text"].encode()) for c in match["context"]) + len(match["text"].encode())
            if len(results) == result_limit or used > 32768:
                truncated = True
                break
            results.append(match)
        if truncated:
            break
    return ToolResult("ok", {"query": query, "matches": results,
                            "returned_matches": len(results), "truncated": truncated},
                      metadata={"snapshot_id": context.repository.snapshot_id})
