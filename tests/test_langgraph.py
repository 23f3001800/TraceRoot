from traceroot.agents.investigator import Budget
from traceroot.agents.langgraph import build_graph, investigate_graph
from traceroot.agents.state import load_state
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import ModelFailure, ModelReply
from test_investigator import active, task, logs_output, source_output, evidence
from test_recovery import reproduction_output

class GraphProvider:
    def __init__(self, replies, retries=1):
        self.config = LLMConfig(max_transient_retries=retries)
        self.replies = iter(replies)
        self.requests = []
    def generate(self, system, messages, schema, timeout):
        self.requests.append((system, messages, schema))
        reply = next(self.replies)
        if isinstance(reply, BaseException):
            raise reply
        return ModelReply(reply, {"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 0})

def hypothesis(status="supported", evidence_items=None):
    return {"id": "H1", "claim": "Configured destination differs from the observed destination.",
            "status": status, "confidence": "high" if status == "supported" else "low",
            "evidence": evidence_items or [], "missing_evidence": [] if status != "proposed" else ["Runtime evidence."]}

def decision(action, hypotheses, reviewed_step=2, ready=False):
    return {"reviewed_step": reviewed_step, "hypotheses": hypotheses,
            "hypothesis_summary": "Evidence narrows the connection mismatch.",
            "evidence_summary": "Runtime and source observations are available.",
            "action": action, "ready_for_evaluation": ready}

def final_report():
    items = [evidence(2, "/data/entries/0/message", "connection refused to port 9001"),
             evidence(3, "/data/lines/0/text", "configured_port = 9000")]
    return {"status": "ROOT_CAUSE_IDENTIFIED", "symptom": "A request fails.", "reproduction_status": "CONFIRMED",
            "root_cause": "Configured destination differs from the observed destination.",
            "root_cause_category": "configuration", "affected_subsystem": "connection setup", "evidence": items,
            "rejected_hypotheses": [], "confidence": "high", "recommended_next_action": "Review the verified configuration mismatch.",
            "limitations": []}

def evaluation_yes():
    return {"decision": "YES", "reason": "Independent runtime and source citations support the supported hypothesis.",
            "final_report": final_report()}

def configure_tools(monkeypatch):
    import traceroot.agents.langgraph as module
    monkeypatch.setitem(module.TOOLS, "run_reproduction", lambda *a, **kw: reproduction_output())
    monkeypatch.setitem(module.TOOLS, "read_logs", lambda *a, **kw: logs_output())
    monkeypatch.setitem(module.TOOLS, "read_file", lambda *a, **kw: source_output())

def graph_replies(active):
    source_and_runtime = [evidence(2, "/data/entries/0/message", "connection refused to port 9001"),
                          evidence(3, "/data/lines/0/text", "configured_port = 9000")]
    return [
        decision({"name": "read_file", "arguments": {"repository": active.repository.source, "file_path": "app/main.py"}},
                 [hypothesis("proposed", [source_and_runtime[0]])]),
        decision(None, [hypothesis("supported", source_and_runtime)], reviewed_step=3, ready=True),
        evaluation_yes(),
    ]

def test_langgraph_has_explicit_nodes_and_conditional_routing(active):
    from traceroot.agents.langgraph import GraphRuntime, _initial_state
    provider = GraphProvider([])
    state = _initial_state(active, task(active), provider, Budget())
    directory = active.session_dir / "agent-runs" / state["run_id"]
    directory.mkdir(parents=True)
    graph = build_graph(GraphRuntime(active, provider, Budget(), directory, state))
    assert {"reproduce", "collect_runtime_evidence", "investigate", "evaluate_evidence",
            "recovery", "report_limitation", "root_cause_report", "finalize", "check_budget"} <= set(graph.get_graph().nodes)

def test_bug_investigates_through_graph_and_finalizes_supported_root_cause(active, monkeypatch):
    configure_tools(monkeypatch)
    result = investigate_graph(active, task(active), GraphProvider(graph_replies(active)))
    assert result["final"]["status"] == "ROOT_CAUSE_IDENTIFIED"
    assert result["summary"]["orchestrator"] == "langgraph"
    assert result["summary"]["tools_used"] == ["run_reproduction", "read_logs", "read_file"]
    saved = load_state(active, result["summary"]["run_id"])
    assert saved["incident"]["bug_report"] == "A request fails."
    assert saved["step_count"] == 3 and saved["provider_errors"] == []
    assert "evaluate_evidence" in [e["node"] for e in saved["events"] if e["event"] == "graph_transition"]

def test_provider_failure_routes_to_recovery_then_resume_without_reproduction(active, monkeypatch):
    configure_tools(monkeypatch)
    failed = investigate_graph(active, task(active), GraphProvider([
        ModelFailure("provider_error", "Gemini request failed (503).", True),
        ModelFailure("provider_error", "Gemini request failed (503).", True),
    ], retries=1))
    assert failed["final"]["status"] == "TOOL_FAILURE" and failed["summary"]["phase"] == "paused"
    resumed = investigate_graph(active, None, GraphProvider(graph_replies(active)), resume_run_id=failed["summary"]["run_id"])
    assert resumed["final"]["status"] == "ROOT_CAUSE_IDENTIFIED"
    assert resumed["summary"]["tools_used"] == ["run_reproduction", "read_logs", "read_file"]
    assert resumed["summary"]["resume_count"] == 1
    assert load_state(active, resumed["summary"]["run_id"])["provider_errors"][0]["code"] == "provider_error"

def test_budget_routes_to_limitation_without_model_call(active, monkeypatch):
    configure_tools(monkeypatch)
    result = investigate_graph(active, task(active), GraphProvider([]), Budget(max_tool_calls=1))
    assert result["final"]["status"] == "MAX_STEPS_REACHED"
    assert result["summary"]["tools_used"] == ["run_reproduction"] and result["summary"]["model_calls"] == 0

def test_blocked_evaluation_routes_to_insufficient_evidence(active, monkeypatch):
    configure_tools(monkeypatch)
    replies = [
        decision({"name": "read_file", "arguments": {"repository": active.repository.source, "file_path": "app/main.py"}}, [hypothesis("proposed")]),
        decision(None, [hypothesis("proposed")], reviewed_step=3, ready=True),
        {"decision": "BLOCKED", "reason": "No approved source is available.", "final_report": None},
    ]
    result = investigate_graph(active, task(active), GraphProvider(replies))
    assert result["final"]["status"] == "INSUFFICIENT_EVIDENCE" and result["summary"]["graph_next"] == "finalize"
