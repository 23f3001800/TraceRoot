"""Credential-reference-only deployed-runtime evidence adapters."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from .contracts import ToolError, ToolResult

_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_SECRET_KEY = re.compile(r"(?i)(token|password|secret|api.?key|authorization)")


@dataclass(frozen=True)
class RuntimeConnectorConfig:
    name: str
    credential_reference: str
    scopes: tuple[str, ...]
    enabled: bool = False

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", self.name):
            raise ValueError("connector name")
        if not _REFERENCE.fullmatch(self.credential_reference):
            raise ValueError("credential reference")
        if not self.scopes or any(scope not in {"logs.read", "metrics.read", "traces.read", "database.read"} for scope in self.scopes):
            raise ValueError("read-only scopes required")


class RuntimeClient(Protocol):
    def read(self, query: dict) -> dict: ...


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class RuntimeEvidenceGateway:
    def __init__(self, connectors: dict[str, tuple[RuntimeConnectorConfig, RuntimeClient]]):
        self.connectors = dict(connectors)

    def read(self, name: str, query: dict) -> ToolResult:
        item = self.connectors.get(name)
        if not item or not isinstance(query, dict):
            return ToolResult("rejected", error=ToolError("runtime_connector_denied", "Unknown runtime connector or invalid query."))
        config, client = item
        if not config.enabled:
            return ToolResult("rejected", error=ToolError("runtime_connector_disabled", "Runtime connector requires explicit operator enablement."))
        try:
            data = client.read(redact(query))
        except Exception:
            return ToolResult("error", error=ToolError("runtime_connector_failure", "Runtime evidence connector failed."))
        return ToolResult("ok", data=redact(data), metadata={"connector": config.name, "credential_reference": config.credential_reference, "scopes": list(config.scopes), "permission": "read"})
