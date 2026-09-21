"""Autonomous, read-only incident detection for deployed AI applications.

The monitor deliberately stops at a proposal.  It never changes a deployment,
retries paid work, or edits source without the existing human approval path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .agents.auditor import AUDITOR_PROMPT, audit_request
from .agents.schemas import AUDIT_SCHEMA, validate
from .agents.state import atomic_json
from .runtime_connectors import redact
from .workspace_events import IncidentStore


_ALLOWED_SCHEMES = {"https"}
_TERMINAL_JOB_FAILURES = {"failed", "cancelled"}
_PROVIDER_OUTCOMES = {"429", "rate_limited", "timeout", "provider_error", "unavailable"}


class AuditProvider(Protocol):
    def generate(self, system: str, messages: list[dict], schema: dict, timeout: float): ...


@dataclass(frozen=True)
class MonitorConfig:
    name: str
    base_url: str
    repository: str
    credential_reference: str = "AZURE_CLI"
    timeout_seconds: float = 10.0
    watched_job_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname or parsed.username:
            raise ValueError("monitor base_url must be an HTTPS origin")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("monitor base_url must not include a path, query, or fragment")
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", self.name):
            raise ValueError("invalid monitor name")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", self.credential_reference):
            raise ValueError("credentials must be referenced, never embedded")
        if not 1 <= self.timeout_seconds <= 30:
            raise ValueError("timeout must be between 1 and 30 seconds")
        if len(self.watched_job_ids) > 20 or any(
            not re.fullmatch(r"[0-9a-fA-F-]{36}", value) for value in self.watched_job_ids
        ):
            raise ValueError("watched job IDs must be bounded UUIDs")


class EduForgeTelemetryClient:
    """Bounded public telemetry reads for the deployed EduForge application."""

    MAX_BYTES = 512 * 1024

    def __init__(self, config: MonitorConfig):
        self.config = config

    def _read(self, path: str, content_type: str) -> bytes:
        url = urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))
        request = Request(url, headers={"Accept": content_type, "User-Agent": "TraceRoot-monitor/1"})
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = response.read(self.MAX_BYTES + 1)
            if len(payload) > self.MAX_BYTES:
                raise ValueError("telemetry response exceeded the bounded read limit")
            return payload

    def _json(self, path: str) -> dict[str, Any]:
        value = json.loads(self._read(path, "application/json"))
        if not isinstance(value, dict):
            raise ValueError("telemetry response must be an object")
        return redact(value)

    def collect(self) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        values: dict[str, Any] = {}
        for key, path in (("health", "/healthz"), ("readiness", "/readyz"),
                          ("stats", "/api/v1/stats")):
            try:
                values[key] = self._json(path)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append({"source": key, "type": type(exc).__name__})
        try:
            values["metrics"] = parse_prometheus(self._read("/metrics", "text/plain").decode("utf-8", "replace"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append({"source": "metrics", "type": type(exc).__name__})
        values["jobs"] = []
        for job_id in self.config.watched_job_ids:
            try:
                values["jobs"].append(self._json(f"/api/v1/jobs/{job_id}"))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append({"source": f"job:{job_id}", "type": type(exc).__name__})
        return {"application": self.config.name, "base_url": self.config.base_url,
                "collected_at": datetime.now(timezone.utc).isoformat(), **values,
                "collector_errors": errors}


def parse_prometheus(text: str) -> dict[str, float]:
    """Return bounded counter series; labels stay in the key for correlation."""
    result: dict[str, float] = {}
    for line in text.splitlines()[:10000]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2 or not parts[0].startswith("eduforge_"):
            continue
        try:
            result[parts[0][:500]] = float(parts[1])
        except ValueError:
            continue
    return result


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _delta(current: float, previous: float) -> float:
    # In-process metrics reset on deployment. Treat the new value as the delta.
    return current - previous if current >= previous else current


def _counters(snapshot: dict[str, Any]) -> dict[str, float]:
    stats = snapshot.get("stats") if isinstance(snapshot.get("stats"), dict) else {}
    jobs = stats.get("jobs") if isinstance(stats.get("jobs"), dict) else {}
    llm = stats.get("llm") if isinstance(stats.get("llm"), dict) else {}
    outcomes = llm.get("by_outcome") if isinstance(llm.get("by_outcome"), dict) else {}
    counters = {"jobs.failed": _number(jobs.get("failed")),
                "jobs.succeeded": _number(jobs.get("succeeded")),
                "llm.attempts": _number(llm.get("attempts"))}
    for name, value in outcomes.items():
        counters[f"llm.outcome.{str(name)[:80]}"] = _number(value)
    return counters


def detect(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Detect runtime and AI failures from measured changes, never inferred trends."""
    signals: list[dict[str, Any]] = []
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    ready = snapshot.get("readiness") if isinstance(snapshot.get("readiness"), dict) else {}
    if health.get("status") != "ok" or ready.get("status") != "ok":
        signals.append({"kind": "runtime", "source": "health/readiness", "value": {
            "health": health.get("status", "unavailable"), "readiness": ready.get("status", "unavailable")}})
    if snapshot.get("collector_errors"):
        signals.append({"kind": "runtime", "source": "telemetry-collector",
                        "value": snapshot["collector_errors"]})

    now, before = _counters(snapshot), _counters(previous or {})
    failed_delta = _delta(now.get("jobs.failed", 0), before.get("jobs.failed", 0))
    if failed_delta > 0:
        signals.append({"kind": "application", "source": "stats.jobs.failed",
                        "value": failed_delta, "counter": now["jobs.failed"]})
    for key, value in now.items():
        if not key.startswith("llm.outcome.") or key.endswith(".ok"):
            continue
        change = _delta(value, before.get(key, 0))
        if change <= 0:
            continue
        outcome = key.removeprefix("llm.outcome.")
        kind = "provider" if outcome.casefold() in _PROVIDER_OUTCOMES else "model"
        signals.append({"kind": kind, "source": key, "outcome": outcome,
                        "value": change, "counter": value})
    previous_jobs = {job.get("job_id"): job for job in (previous or {}).get("jobs", [])
                     if isinstance(job, dict) and job.get("job_id")}
    for job in snapshot.get("jobs", []):
        if not isinstance(job, dict) or not job.get("job_id"):
            continue
        prior_status = (previous_jobs.get(job["job_id"]) or {}).get("status")
        status = job.get("status")
        if status in _TERMINAL_JOB_FAILURES | {"succeeded_partial"} and status != prior_status:
            signals.append({"kind": "application", "source": f"job:{job['job_id']}",
                            "status": status, "progress": job.get("progress"),
                            "usage": job.get("usage"), "error": job.get("error")})
        for warning in job.get("warnings") or []:
            if status == "succeeded_partial" and status != prior_status:
                signals.append({"kind": "model", "source": f"job:{job['job_id']}:warning",
                                "outcome": "quality_degradation", "warning": str(warning)[:500]})
    return signals


def correlate(signals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = [{"step": index, "pointer": f"runtime:{item['source']}",
                 "quote": json.dumps(redact(item), sort_keys=True)[:800],
                 "supports": f"Measured {item['kind']} failure signal"}
                for index, item in enumerate(signals, 1)]
    kinds = {item["kind"] for item in signals}
    if "application" in kinds and "provider" in kinds:
        claim = "A provider failure coincided with an EduForge job failure in the same monitoring interval."
    elif "application" in kinds and "model" in kinds:
        claim = "A model-quality degradation caused EduForge to complete the watched job only partially."
    elif "runtime" in kinds:
        claim = "The deployed EduForge runtime or its telemetry endpoint is unavailable."
    else:
        claim = "EduForge reported a failed job, but component-level cause is not yet established."
    hypothesis = {"id": "H1", "claim": claim, "status": "supported" if len(kinds) >= 2 else "proposed",
                  "confidence": "high" if len(kinds) >= 2 else "low", "evidence": evidence,
                  "missing_evidence": [] if len(kinds) >= 2 else ["Independent component-level failure evidence"]}
    return evidence, [hypothesis]


class AutonomousMonitor:
    def __init__(self, config: MonitorConfig, client: EduForgeTelemetryClient,
                 store: IncidentStore, state_file: Path, auditor: AuditProvider):
        self.config, self.client, self.store = config, client, store
        self.state_file, self.auditor = Path(state_file), auditor

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def run_once(self) -> dict[str, Any]:
        prior = self._load_state()
        snapshot = self.client.collect()
        signals = detect(snapshot, prior.get("snapshot"))
        signature = hashlib.sha256(json.dumps(signals, sort_keys=True).encode()).hexdigest() if signals else ""
        result: dict[str, Any] = {"status": "healthy" if not signals else "detected",
                                  "signals": signals, "snapshot": snapshot}
        if signals and signature != prior.get("last_signature"):
            result.update(self._investigate(snapshot, signals))
        elif signals:
            result["status"] = "duplicate_suppressed"
        atomic_json(self.state_file, {"snapshot": snapshot, "last_signature": signature or prior.get("last_signature"),
                                      "updated_at": snapshot["collected_at"]})
        return result

    def _investigate(self, snapshot: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
        evidence, hypotheses = correlate(signals)
        report = f"Automatically detected {len(signals)} failure signal(s) from {self.config.name}; no manual bug report was supplied."
        incident = self.store.create(self.config.repository, report, runtime=self.config.base_url)
        iid = incident["id"]
        self.store._emit("monitor.failure_detected", {"signals": signals, "connector": self.config.name}, iid, "Detection")
        self.store._emit("evidence.collected", {"evidence": evidence, "snapshot": snapshot}, iid, "Runtime evidence")
        self.store._emit("hypothesis.updated", {"hypotheses": hypotheses}, iid, "Investigation")
        audit_state = {"incident": incident, "reproduction": {"status": "RUNTIME_OBSERVED"},
                       "observations": signals, "hypotheses": hypotheses, "evidence": evidence}
        reply = self.auditor.generate(AUDITOR_PROMPT, audit_request(audit_state), AUDIT_SCHEMA, 60)
        validate(reply.decision, AUDIT_SCHEMA)
        self.store._emit("audit.completed", {"audit": reply.decision, "usage": redact(reply.usage)}, iid, "Evidence audit")
        incident.update({"status": "AUDITED" if reply.decision["verdict"] == "SUPPORTED" else "NEEDS_EVIDENCE",
                         "audit": reply.decision, "signals": signals,
                         "remediation": {"status": "REQUIRES_HUMAN_APPROVAL", "executed": False,
                                         "proposal": "Retry only the failed checkpoint after provider health is confirmed."}})
        self.store.save(incident)
        self.store._emit("remediation.proposed", incident["remediation"], iid, "Remediation")
        return {"status": "audited", "incident_id": iid, "audit": reply.decision,
                "remediation": incident["remediation"]}

    def run_forever(self, interval_seconds: int) -> None:
        if not 10 <= interval_seconds <= 3600:
            raise ValueError("poll interval must be between 10 and 3600 seconds")
        while True:
            print(json.dumps(self.run_once(), sort_keys=True), flush=True)
            time.sleep(interval_seconds)


__all__ = ["AutonomousMonitor", "EduForgeTelemetryClient", "MonitorConfig", "correlate", "detect", "parse_prometheus"]
