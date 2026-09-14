from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..contracts import ToolFailure, ToolResult, tool
from ..repository import relative_path

_SECRET = re.compile(r"(password|secret|token|api[_-]?key|private[_-]?key)", re.IGNORECASE)
_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*(?:=|:)\s*(.+?)\s*$")

@tool
def inspect_configuration(context, repository: str, file_path: str | None = None,
                          scope: str = "application") -> ToolResult:
    context.repository.validate(repository)
    if scope not in {"application", "build", "test"}:
        raise ToolFailure("invalid_scope", "scope must be application, build, or test.")
    if file_path is not None:
        file_path = relative_path(file_path)
        if file_path not in context.repository.manifest:
            raise ToolFailure("path_denied", "Configuration file is not in the approved snapshot.")
        paths = [file_path]
    elif scope == "application":
        paths = [p for p in context.repository.manifest if p.startswith("app/") and p.endswith(".py") and any(x in p.lower() for x in ("config", "setting", "main"))]
    elif scope == "build":
        paths = [p for p in context.repository.manifest if p in {"requirements.txt", "pyproject.toml", "setup.cfg", "Dockerfile", "docker-compose.yml", "docker-compose.yaml"}]
    else:
        paths = [p for p in context.repository.manifest if p == "pytest.ini" or p.startswith("tests/")]
    entries, truncated = [], False
    for path in sorted(paths)[:20]:
        for number, line in enumerate(context.repository.read(path).splitlines(), 1):
            match = _ASSIGNMENT.match(line)
            if not match:
                continue
            key, value = match.groups()
            redacted = bool(_SECRET.search(key))
            entries.append({"file": path, "line": number, "key": key, "value": "[redacted]" if redacted else value[:1000], "redacted": redacted})
            if len(entries) == 100:
                truncated = True
                break
        if truncated:
            break
    return ToolResult("ok", {"scope": scope, "files": sorted(paths)[:20], "entries": entries, "truncated": truncated}, metadata={"snapshot_id": context.repository.snapshot_id})
