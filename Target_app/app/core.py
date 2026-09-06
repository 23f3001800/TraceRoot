import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

request_id: ContextVar[str] = ContextVar("request_id", default="-")

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "request_id": request_id.get(),
            "message": record.getMessage(),
        }
        for key in ("method", "endpoint", "status", "exception_type", "error_message"):
            if hasattr(record, key):
                result[key] = getattr(record, key)
        if record.exc_info:
            result["traceback"] = self.formatException(record.exc_info)
        return json.dumps(result)

logger = logging.getLogger("target_app")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
logger.propagate = False
