from datetime import datetime, timezone
import json
import re
from ..contracts import ToolFailure, ToolResult, bounded_int, tool, utc_now

def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Timezone required")
    return timestamp.astimezone(timezone.utc)

def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(word in k.lower() for word in
                ("password", "token", "secret", "authorization")) else redact(v, secrets)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(://[^\s:/]+:)[^@\s]+@", r"\1[REDACTED]@", value)
        value = re.sub(r"(?i)(password|token|secret|authorization)(\s*[:=]\s*)(\S+)",
                       r"\1\2[REDACTED]", value)
    return value

@tool
def read_logs(context, source: str = "application", start_time: str | None = None,
              end_time: str | None = None, request_id: str | None = None,
              limit: int = 20, run_id: str | None = None) -> ToolResult:
    if source != "application":
        raise ToolFailure("source_denied", "Only the registered application log source is available.")
    bounded_int(limit, 1, 100, "limit")
    start = parse_time(start_time) if start_time else None
    end = parse_time(end_time) if end_time else None
    if start and end and start > end:
        raise ToolFailure("invalid_window", "start_time must not follow end_time.")
    path = context.session_dir / "application.jsonl"
    if not path.exists():
        raise ToolFailure("logs_unavailable", "No application logs have been collected.", "unavailable")
    if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ToolFailure("log_source_limit", "Log source is unsafe or exceeds the collection limit.", "error")
    entries, collector_errors, missing = [], [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict):
                raise ValueError()
            stamp = parse_time(entry["timestamp"]) if "timestamp" in entry else None
        except (ValueError, TypeError, KeyError):
            collector_errors.append({"line": number, "code": "malformed_record"})
            continue
        if request_id is not None and entry.get("request_id") != request_id:
            continue
        if run_id is not None and entry.get("run_id") != run_id:
            continue
        if (start or end) and stamp is None:
            missing.append({"line": number, "fields": ["timestamp"], "excluded_from_time_filter": True})
            continue
        if start and stamp < start or end and stamp > end:
            continue
        absent = [key for key in ("timestamp", "request_id") if key not in entry]
        if absent:
            missing.append({"line": number, "fields": absent})
        entries.append((stamp or datetime.min.replace(tzinfo=timezone.utc), number, entry))
    entries.sort(key=lambda row: (row[0], row[1]))
    result, used = [], 0
    secrets = [context.config.get(k, "") for k in ("app_password", "inspector_password", "admin_password")]
    for _, _, entry in entries[:limit]:
        entry = redact(entry, secrets)
        # Tracebacks remain obtainable as bounded messages; never flood the context.
        if isinstance(entry.get("traceback"), str) and len(entry["traceback"]) > 3000:
            entry["traceback"] = entry["traceback"][:3000]
            entry["traceback_truncated"] = True
        serialized = json.dumps(entry)
        if used + len(serialized.encode()) > 32768:
            break
        used += len(serialized.encode())
        result.append(entry)
    data = {"source": source, "collected_at": utc_now(), "entries": result,
            "truncated": len(result) < len(entries), "missing_fields": missing[:100],
            "collector_errors": collector_errors[:100]}
    if collector_errors:
        from ..contracts import ToolError
        return ToolResult("error", data, ToolError("collector_error", "Some log records could not be collected."))
    return ToolResult("ok", data)
