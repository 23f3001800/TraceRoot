import json
from pathlib import Path

from traceroot.autonomous_monitor import (AutonomousMonitor, MonitorConfig, correlate, detect,
                                          parse_prometheus, remediation_proposal)
from traceroot.llms.provider import ModelReply
from traceroot.workspace_events import IncidentStore


class Client:
    def __init__(self, snapshot): self.snapshot = snapshot
    def collect(self): return self.snapshot


class Auditor:
    def generate(self, system, messages, schema, timeout):
        body = json.loads(messages[0]["text"])
        assert "tools" not in body
        evidence = body["evidence"]
        return ModelReply({"verdict": "SUPPORTED", "unsupported_claims": [], "missing_evidence": [],
            "required_next_evidence": [], "reason": "Job and provider counters independently agree.",
            "evidence_supporting": evidence}, {"input_tokens": 100, "output_tokens": 40})


def snapshot(failed=0, ok=0, provider_error=0):
    return {"application": "eduforge-ai", "base_url": "https://example.test",
        "collected_at": "2026-09-20T12:00:00+00:00", "health": {"status": "ok"},
        "readiness": {"status": "ok", "llm_profile": "azure"}, "collector_errors": [],
        "stats": {"jobs": {"failed": failed, "succeeded": ok},
                  "llm": {"attempts": ok + provider_error,
                          "by_outcome": {"ok": ok, "provider_error": provider_error}}}}


def test_prometheus_parser_is_bounded_to_application_metrics():
    parsed = parse_prometheus('# help\neduforge_jobs_total 2\npython_gc 99')
    assert parsed == {'eduforge_jobs_total': 2.0}


def test_detection_correlates_job_and_provider_deltas():
    signals = detect(snapshot(2, 4, 2), snapshot(1, 4, 1))
    assert {item["kind"] for item in signals} == {"application", "provider"}
    evidence, hypotheses = correlate(signals)
    assert len(evidence) == 2
    assert hypotheses[0]["status"] == "supported"


def test_monitor_creates_audited_incident_and_suppresses_duplicate(tmp_path: Path):
    current = snapshot(1, 0, 1)
    store = IncidentStore(tmp_path / "workspace")
    monitor = AutonomousMonitor(MonitorConfig("eduforge-ai", "https://example.test", "https://github.com/example/app"),
        Client(current), store, tmp_path / "cursor.json", Auditor())
    first = monitor.run_once()
    assert first["status"] == "audited"
    incident = store.get(first["incident_id"])
    assert incident["status"] == "AUDITED"
    assert incident["remediation"]["executed"] is False
    # Counters did not advance, so the next sample is healthy and creates no duplicate.
    assert monitor.run_once()["status"] == "healthy"
    assert len(store.list()) == 1


def test_no_incident_for_healthy_telemetry(tmp_path: Path):
    store = IncidentStore(tmp_path / "workspace")
    result = AutonomousMonitor(MonitorConfig("eduforge-ai", "https://example.test", "repo"),
        Client(snapshot()), store, tmp_path / "cursor.json", Auditor()).run_once()
    assert result["status"] == "healthy"
    assert store.list() == []


def test_partial_job_and_quality_warning_trigger_cross_component_evidence():
    current = snapshot()
    current["jobs"] = [{"job_id": "446c7d47-1e03-41fa-a432-a47aea05557e",
        "status": "succeeded_partial", "progress": 100,
        "usage": {"tokens": 30835, "cost_usd": 0.0},
        "warnings": ["educational-classification: low confidence: grade_band"], "error": None}]
    signals = detect(current, snapshot())
    assert {signal["kind"] for signal in signals} == {"application", "model"}
    assert correlate(signals)[1][0]["status"] == "supported"
    assert "educational-classification checkpoint" in remediation_proposal(signals)
