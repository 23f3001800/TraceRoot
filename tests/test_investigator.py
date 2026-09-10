import json
from pathlib import Path
import time
import pytest

from traceroot.agents.investigator import Budget, investigate
from traceroot.agents.schemas import CATALOG, DECISION_SCHEMA, FINAL_SCHEMA, validate
from traceroot.contracts import ToolResult
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import ModelFailure, ModelReply, load_api_key

class FakeProvider:
    config = LLMConfig()
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.requests = []
    def generate(self, system, messages, schema, timeout):
        self.requests.append((system, messages))
        decision = next(self.decisions)
        current = json.loads(messages[-1]['text'])['state']
        decision.setdefault('reviewed_step', current['latest_tool_step'])
        if 'hypotheses' not in decision:
            final = decision.get('final_report')
            if final and final['root_cause']:
                decision['hypotheses'] = [*current['hypotheses'], {
                    'id': 'H9', 'claim': final['root_cause'], 'status': 'supported',
                    'confidence': 'medium', 'evidence': final['evidence'], 'missing_evidence': []}]
            else:
                decision['hypotheses'] = current['hypotheses'] or ([{
                    'id': 'H1', 'claim': 'The request may fail during dependency access.',
                    'status': 'proposed', 'confidence': 'low', 'evidence': [],
                    'missing_evidence': ['Runtime and source confirmation.']} ] if current['latest_tool_step'] else [])
        return ModelReply(decision, {"input_tokens": 10, "output_tokens": 5})

@pytest.fixture
def active(context):
    context.config["active"] = True
    return context

def task(context):
    return {"repository": context.repository.source, "bug_report": "A request fails.",
            "constraints": ["read-only investigation", "benchmark folder forbidden",
                            "no code changes", "no database changes"]}

def action(name, arguments):
    return {"hypothesis_summary": "More evidence is required.", "evidence_summary": "Observe the selected subsystem.",
            "action": {"name": name, "arguments": arguments}, "final_report": None}

def report(status="INSUFFICIENT_EVIDENCE", reproduction="NOT_ATTEMPTED", evidence=None):
    return {"status": status, "symptom": "A request fails.", "reproduction_status": reproduction,
            "root_cause": "Configured destination differs from the observed destination." if status == "ROOT_CAUSE_IDENTIFIED" else None,
            "root_cause_category": "configuration" if status == "ROOT_CAUSE_IDENTIFIED" else None,
            "affected_subsystem": "connection setup" if status == "ROOT_CAUSE_IDENTIFIED" else None,
            "evidence": evidence or [], "rejected_hypotheses": [], "confidence": "medium",
            "recommended_next_action": "Review the verified configuration mismatch.",
            "limitations": ["Reproduction has not been independently established."]}

def finish(final):
    return {"hypothesis_summary": "Stop at the supported conclusion.", "evidence_summary": "Cited evidence is sufficient for this status.",
            "action": None, "final_report": final}

def output(result):
    return ToolResult("ok", result, metadata={"run_id": "synthetic", "schema_version": "1.0"})

def source_output():
    return output({"file": "app/main.py", "lines": [{"line": 1, "text": "configured_port = 9000"}],
                   "total_lines": 1, "sha256": "a"*64, "truncated": False, "next_line": None})

def logs_output():
    return output({"source": "application", "collected_at": "2026-09-07T00:00:00Z",
                   "entries": [{"message": "connection refused to port 9001"}],
                   "truncated": False, "missing_fields": [], "collector_errors": []})

def evidence(step, pointer, quote):
    return {"step": step, "pointer": pointer, "quote": quote, "supports": "Observed configuration behavior."}

def test_exactly_six_neutral_contracts():
    from traceroot.tools import TOOLS
    assert {c["name"] for c in CATALOG} == set(TOOLS)
    text = json.dumps(CATALOG).lower()
    assert all(word not in text for word in ("discount", "services.py", "models.py", "order_total_consistent"))
    for entry in CATALOG:
        assert set(entry) == {"name", "description", "input_schema", "output_schema"}
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(DECISION_SCHEMA)
    Draft202012Validator.check_schema(FINAL_SCHEMA)

def test_no_forced_sequence_or_requirement_to_use_every_tool(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, "read_logs", lambda *a, **kw: logs_output())
    monkeypatch.setitem(module.TOOLS, "read_file", lambda *a, **kw: source_output())
    final = report("ROOT_CAUSE_IDENTIFIED", evidence=[
        evidence(1, "/data/entries/0/message", "connection refused to port 9001"),
        evidence(2, "/data/lines/0/text", "configured_port = 9000"),
    ])
    provider = FakeProvider([action("read_logs", {}), action("read_file", {
        "repository": active.repository.source, "file_path": "app/main.py"}), finish(final)])
    result = investigate(active, task(active), provider)
    assert result["final"]["status"] == "ROOT_CAUSE_IDENTIFIED"
    assert result["summary"]["tools_used"] == ["read_logs", "read_file"]
    assert result["summary"]["tool_calls"] == 2

def test_code_alone_cannot_be_declared_root_cause(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, "read_file", lambda *a, **kw: source_output())
    final = report("ROOT_CAUSE_IDENTIFIED", evidence=[evidence(1, "/data/lines/0/text", "configured_port = 9000")])
    provider = FakeProvider([action("read_file", {"repository": active.repository.source, "file_path": "app/main.py"}),
                             finish(final), finish(report())])
    result = investigate(active, task(active), provider)
    assert result["final"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["summary"]["invalid_decisions"] == 1

@pytest.mark.parametrize("bad", [
    evidence(8, "/data/lines/0/text", "made up"),
    evidence(1, "/data/lines/999/text", "made up"),
    evidence(1, "/data/lines/0/text", "fabricated quote"),
    evidence(1, "/metadata/run_id", "synthetic"),
])
def test_fabricated_evidence_rejected(active, monkeypatch, bad):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, "read_file", lambda *a, **kw: source_output())
    provider = FakeProvider([action("read_file", {"repository": active.repository.source, "file_path": "app/main.py"}),
                             finish(report("ROOT_CAUSE_IDENTIFIED", evidence=[bad])), finish(report())])
    result = investigate(active, task(active), provider)
    assert result["summary"]["invalid_decisions"] == 1

def test_tool_budget_stops_before_extra_execution(active, monkeypatch):
    import traceroot.agents.investigator as module
    called = []
    def tool(*a, **kw):
        called.append(True)
        return logs_output()
    monkeypatch.setitem(module.TOOLS, "read_logs", tool)
    provider = FakeProvider([action("read_logs", {}), action("read_logs", {})])
    result = investigate(active, task(active), provider, Budget(max_tool_calls=1))
    assert len(called) == 1
    assert result["final"]["status"] == "MAX_STEPS_REACHED"
    assert result["summary"]["stopping_reason"] == "tool_call_budget"

def test_model_time_budget_is_enforced(active):
    class Slow(FakeProvider):
        def generate(self, *args):
            time.sleep(3)
    start = time.monotonic()
    result = investigate(active, task(active), Slow([]), Budget(max_seconds=1))
    assert result["summary"]["stopping_reason"] == "time_budget"
    assert time.monotonic() - start < 2

def test_individual_model_timeout_is_not_false_success(active):
    class Slow(FakeProvider):
        def generate(self, *args):
            time.sleep(3)
    result = investigate(active, task(active), Slow([]), Budget(max_seconds=20, model_timeout=1))
    assert result["final"]["status"] == "TOOL_FAILURE"
    assert result["summary"]["stopping_reason"] == "model_timeout"

def test_tool_deadline_is_enforced(active, monkeypatch):
    import traceroot.agents.investigator as module
    def slow(*a, **kw):
        time.sleep(3)
        return logs_output()
    monkeypatch.setitem(module.TOOLS, "read_logs", slow)
    result = investigate(active, task(active), FakeProvider([action("read_logs", {})]), Budget(max_seconds=1))
    assert result["final"]["status"] == "MAX_STEPS_REACHED"
    assert active.operation_deadline is None

def test_private_thoughts_are_not_saved(active):
    invalid = {**finish(report()), "private_thought": "PRIVATE_REASONING_SENTINEL"}
    result = investigate(active, task(active), FakeProvider([invalid, invalid, invalid]))
    assert result["final"]["status"] == "TOOL_FAILURE"
    artifact_text = "".join(p.read_text() for p in Path(result["summary"]["artifacts"]).iterdir())
    assert "PRIVATE_REASONING_SENTINEL" not in artifact_text

def test_no_operator_context_or_credentials_in_model_input(active):
    provider = FakeProvider([finish(report())])
    investigate(active, task(active), provider)
    text = json.dumps(provider.requests)
    assert "a-secret" not in text and "admin-secret" not in text
    assert "session.json" not in text and "manifest" not in text
    assert "EVALUATOR_SENTINEL" not in text

@pytest.mark.parametrize("field", ["root_cause", "affected_file", "expected_patch", "failing_line"])
def test_task_rejects_answer_hints(active, field):
    with pytest.raises(ValueError):
        investigate(active, {**task(active), field: "hint"}, FakeProvider([]))

def test_read_only_boundaries_survive_injected_tool_request(active):
    request = action("read_file", {"repository": active.repository.source, "file_path": "benchmarks/bug-001/README.md"})
    result = investigate(active, task(active), FakeProvider([request, finish(report())]))
    assert result["summary"]["incorrect_calls"] == 1
    text = (Path(result["summary"]["artifacts"]) / "trajectory.jsonl").read_text()
    assert "EVALUATOR_SENTINEL" not in text

def test_tool_failure_is_observed_and_can_be_reported(active, monkeypatch):
    import traceroot.agents.investigator as module
    from traceroot.contracts import ToolError
    monkeypatch.setitem(module.TOOLS, "run_reproduction", lambda *a, **kw: ToolResult(
        "unavailable", error=ToolError("no_reproduction", "No public reproduction.")))
    provider = FakeProvider([action("run_reproduction", {"repository_path": active.repository.source}),
                             finish(report("REPRODUCTION_FAILED", "UNAVAILABLE"))])
    result = investigate(active, task(active), provider)
    assert result["final"]["reproduction_status"] == "UNAVAILABLE"
    assert result["final"]["status"] == "REPRODUCTION_FAILED"

def test_invalid_tool_output_is_structured(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, "read_logs", lambda *a, **kw: output({"wrong": "shape"}))
    result = investigate(active, task(active), FakeProvider([action("read_logs", {}), finish(report("TOOL_FAILURE"))]))
    events = [json.loads(line) for line in (Path(result["summary"]["artifacts"]) / "trajectory.jsonl").read_text().splitlines()]
    assert next(e for e in events if e["event"] == "tool_result")["result"]["error"]["code"] == "output_contract_failed"

def test_missing_key_and_env_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ModelFailure):
        load_api_key()
    path = tmp_path / ".env"
    path.write_text("UNRELATED=do-not-load\nGEMINI_API_KEY='local-key'\n")
    assert load_api_key(path) == "local-key"
    assert os_environ_missing("UNRELATED")

def os_environ_missing(name):
    import os
    return name not in os.environ

def test_gemini_retry_is_bounded_and_transient_only():
    from traceroot.llms.config import LLMConfig
    from traceroot.llms.provider import retry_options
    options = retry_options(LLMConfig())
    assert options.attempts == 1  # Retries belong to the checkpointed runner.
    assert options.initial_delay == 0.5
    assert options.max_delay == 0.5
    assert options.http_status_codes == [429, 500, 502, 503, 504]
    assert retry_options(LLMConfig(max_transient_retries=0)).attempts == 1
    with pytest.raises(ValueError):
        LLMConfig(max_transient_retries=4)
