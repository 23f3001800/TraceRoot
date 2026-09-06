from ..repository import relative_path
from ..contracts import ToolResult, bounded_int, tool

@tool
def read_file(context, repository: str, file_path: str,
              start_line: int = 1, end_line: int = 80) -> ToolResult:
    context.repository.validate(repository)
    file_path = relative_path(file_path)
    bounded_int(start_line, 1, 1000000, "start_line")
    bounded_int(end_line, start_line, start_line + 199, "end_line")
    content = context.repository.read(file_path)
    lines = content.splitlines()
    selected = [{"line": i + 1, "text": line} for i, line in
                enumerate(lines[start_line - 1:end_line], start_line - 1)]
    # Per-file bytes are bounded; output is additionally bounded to 32 KiB.
    budget, output = 0, []
    for line in selected:
        budget += len(line["text"].encode()) + 32
        if budget > 32768:
            break
        output.append(line)
    truncated = len(output) < len(selected) or end_line < len(lines)
    return ToolResult("ok", {
        "file": file_path, "lines": output, "total_lines": len(lines),
        "sha256": context.repository.manifest[file_path],
        "truncated": truncated, "next_line": output[-1]["line"] + 1 if truncated and output else None,
    }, metadata={"snapshot_id": context.repository.snapshot_id})
