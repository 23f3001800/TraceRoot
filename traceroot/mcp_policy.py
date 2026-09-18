"""Explicit MCP permission policy. Investigation MCP access is read-only."""
from __future__ import annotations

MCP_ACCESS_MODE = "read_only"
ALLOWED_READ_ONLY_FAMILIES = frozenset({"git", "runtime", "database"})
DENIED_WRITE_VERBS = frozenset({"apply", "commit", "push", "delete", "update", "insert", "restart", "deploy"})

def is_read_only_tool(name: str) -> bool:
    family = name.split(".", 1)[0]
    operation = name.rsplit(".", 1)[-1].casefold()
    return family in ALLOWED_READ_ONLY_FAMILIES and operation not in DENIED_WRITE_VERBS
