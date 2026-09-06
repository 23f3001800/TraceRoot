from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

Status = Literal["ok", "rejected", "unavailable", "timeout", "error"]

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class ToolError:
    code: str
    message: str

@dataclass
class ToolResult:
    status: Status
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ToolFailure(Exception):
    def __init__(self, code: str, message: str, status: Status = "rejected"):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

def bounded_int(value: int, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ToolFailure("invalid_input", f"{name} must be an integer from {minimum} to {maximum}.")
    return value

def tool(fn):
    @wraps(fn)
    def call(*args, **kwargs) -> ToolResult:
        started = monotonic()
        metadata = {"schema_version": "1.0", "tool": fn.__name__,
                    "run_id": uuid4().hex, "started_at": utc_now()}
        try:
            result = fn(*args, **kwargs)
        except ToolFailure as exc:
            result = ToolResult(exc.status, error=ToolError(exc.code, exc.message))
        except (ValueError, TypeError):
            result = ToolResult("rejected", error=ToolError("invalid_input", "Invalid input type or value."))
        except OSError:
            result = ToolResult("error", error=ToolError("io_error", "An approved resource could not be accessed."))
        except Exception as exc:
            # Do not expose paths, credentials, or arbitrary exception messages.
            result = ToolResult("error", error=ToolError("internal_error", type(exc).__name__))
        result.metadata = {**metadata, **result.metadata, "finished_at": utc_now(),
                           "duration_ms": round((monotonic() - started) * 1000, 2)}
        return result
    return call
