import json
import re
from uuid import uuid4
from ..contracts import ToolError, ToolFailure, ToolResult, bounded_int, tool
from ..docker_runtime import checked, container_options, docker, inspector_url, require_active

@tool
def inspect_database(context, operation: str, table: str | None = None,
                     columns: list[str] | None = None, filters: dict | None = None,
                     limit: int = 20) -> ToolResult:
    bounded_int(limit, 1, 100, "limit")
    if operation not in {"list_tables", "describe_table", "list_constraints", "sample_rows"}:
        raise ToolFailure("operation_denied", "Only fixed read-only database operations are supported.")
    if operation != "list_tables" and (not isinstance(table, str) or not re.fullmatch(r"[a-z_][a-z_0-9]{0,62}", table)):
        raise ToolFailure("invalid_table", "Use a public table identifier.")
    if columns is not None and (not isinstance(columns, list) or not 1 <= len(columns) <= 30
                              or not all(isinstance(c, str) and re.fullmatch(r"[a-z_][a-z_0-9]{0,62}", c) for c in columns)):
        raise ToolFailure("invalid_columns", "Use a bounded list of plain column identifiers.")
    if filters is not None and (not isinstance(filters, dict) or len(filters) > 10
                              or any(not isinstance(k, str) or not re.fullmatch(r"[a-z_][a-z_0-9]{0,62}", k)
                                     or type(v) not in (str, int, float, bool, type(None))
                                     or len(str(v)) > 200 for k, v in filters.items())):
        raise ToolFailure("invalid_filters", "Use bounded scalar equality filters.")
    require_active(context)
    name = "traceroot-inspect-" + uuid4().hex[:12]
    created = False
    try:
        checked(context, ["create", "-i", *container_options(context, name),
                          "--env", f"INSPECTION_DATABASE_URL={inspector_url(context)}",
                          context.config["image"], "python", "/opt/traceroot/database_worker.py"])
        created = True
        request = {"operation": operation, "table": table, "columns": columns, "filters": filters, "limit": limit}
        result = docker(context, ["start", "-a", "-i", name], 15, json.dumps(request).encode())
        if result.timed_out:
            return ToolResult("timeout", error=ToolError("database_timeout", "Database inspection timed out."))
        if result.exit_code or result.stdout_truncated:
            return ToolResult("error", error=ToolError("database_worker_failed", "Inspection worker failed or exceeded its output limit."))
        payload = json.loads(result.stdout)
        if payload["status"] != "ok":
            error = payload["error"]
            return ToolResult(payload["status"], error=ToolError(error["code"], error["message"]))
        return ToolResult("ok", payload["data"])
    finally:
        if created and docker(context, ["rm", "-f", name]).exit_code:
            raise ToolFailure("cleanup_failed", "Inspection container could not be removed.", "error")
