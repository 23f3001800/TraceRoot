"""Bounded public projection. Never send raw checkpoints to a browser."""
import re

SENSITIVE = re.compile(r"(?i)(password|secret|authorization|api[_-]?key|access[_-]?token|connection[_-]?string|transcript|prompt)")
ASSIGNMENT = re.compile(r"(?i)(bearer\s+)[\w.\-]+|((?:password|api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;]+")
URL_CREDENTIALS = re.compile(r"(\w+://)[^/@\s]+:[^/@\s]+@")

def public(value, depth=0):
    if depth > 8:
        return "[bounded]"
    if isinstance(value, dict):
        return {str(k)[:100]: "[REDACTED]" if SENSITIVE.search(str(k)) else public(v, depth + 1)
                for k, v in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [public(v, depth + 1) for v in value[:100]]
    if isinstance(value, str):
        value = URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
        return ASSIGNMENT.sub(lambda m: (m.group(1) or m.group(2)) + "[REDACTED]", value[:16000])
    return value if value is None or isinstance(value, (int, float, bool)) else str(value)[:200]
