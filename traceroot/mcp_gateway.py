"""Read-only MCP tool gateway; MCP transports capabilities, never agent authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any
from .contracts import ToolError, ToolResult
from .mcp_policy import is_read_only_tool

@dataclass(frozen=True)
class MCPTool:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]

class MCPClient(Protocol):
    def list_tools(self) -> list[MCPTool]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...

class MCPGateway:
    def __init__(self, clients: dict[str, MCPClient]):
        self.clients = dict(clients)

    def discover(self) -> list[dict[str, Any]]:
        tools = []
        for server, client in sorted(self.clients.items()):
            for tool in client.list_tools():
                if is_read_only_tool(tool.name):
                    tools.append({"server": server, "name": tool.name,
                                  "description": tool.description, "input_schema": tool.input_schema,
                                  "permission": "read"})
        return tools

    def invoke(self, server: str, name: str, arguments: dict[str, Any]) -> ToolResult:
        if server not in self.clients or not is_read_only_tool(name):
            return ToolResult("rejected", error=ToolError("mcp_tool_denied", "MCP tool is not permitted."))
        if not isinstance(arguments, dict):
            return ToolResult("rejected", error=ToolError("invalid_input", "MCP arguments must be an object."))
        try:
            result = self.clients[server].call_tool(name, arguments)
        except TimeoutError:
            return ToolResult("timeout", error=ToolError("mcp_transport_timeout", "MCP transport timed out."))
        except Exception:
            return ToolResult("error", error=ToolError("mcp_transport_failure", "MCP transport failed."))
        if not isinstance(result, dict) or result.get("status") not in {"ok", "error"}:
            return ToolResult("error", error=ToolError("mcp_schema_invalid", "MCP response is not structured."))
        if result["status"] == "error":
            return ToolResult("error", error=ToolError("mcp_tool_failure", "MCP tool reported a failure."))
        return ToolResult("ok", data=result.get("data", {}), metadata={"server": server, "tool": name, "permission": "read"})
