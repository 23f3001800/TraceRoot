import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
import urllib.request

import pytest

from traceroot.agents.state import atomic_json, load_state
from traceroot.agents.langgraph import investigate_graph
from traceroot.workspace_events import IncidentStore, WorkspaceProgress
from traceroot.workspace_ui import WorkspaceAPI
from test_investigator import active, task
from test_langgraph import GraphProvider, configure_tools, graph_replies


def test_pause_keeps_next_node_and_resume_consumes_message_once(active, monkeypatch):
    configure_tools(monkeypatch)
    requests = []
    def progress(event):
        requests.append(event)
        if event["event"] == "tool.completed" and event.get("tool") == "run_reproduction":
            atomic_json(active.session_dir / "operator-control.json", {"state": "PAUSE_REQUESTED"})
    paused = investigate_graph(active, task(active), GraphProvider([]), progress=progress)
    assert paused["summary"]["phase"] == "paused"
    assert paused["final"] is None
    state = load_state(active, paused["summary"]["run_id"])
    assert state["graph_next"] == "collect_runtime_evidence"
    (active.session_dir / "operator-events.jsonl").write_text(json.dumps(
        {"id": "m1", "kind": "message", "message": "Inspect deployment history."}) + "\n")
    atomic_json(active.session_dir / "operator-control.json", {"state": "RUNNING"})
    model = GraphProvider(graph_replies(active))
    result = investigate_graph(active, None, model, resume_run_id=state["run_id"])
    assert result["final"]["status"] == "ROOT_CAUSE_SUPPORTED"
    assert result["summary"]["tools_used"].count("run_reproduction") == 1
    assert "Inspect deployment history." in json.dumps(model.requests[0])
    final = load_state(active, state["run_id"])
    assert sum("operator_message" in m["text"] for m in final["transcript"]) == 1


def test_stop_prevents_next_operation(active, monkeypatch):
    configure_tools(monkeypatch)
    atomic_json(active.session_dir / "operator-control.json", {"state": "STOP_REQUESTED"})
    result = investigate_graph(active, task(active), GraphProvider([]))
    assert result["summary"]["phase"] == "stopped"
    assert result["summary"]["tool_calls"] == 0


def test_events_order_replay_and_redaction_across_writers(tmp_path):
    def emit(index):
        IncidentStore(tmp_path)._emit("evidence.added", {"message": "Bearer sensitive-value", "password": "secret"},
                                      "left" if index % 2 else "right")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(emit, range(20)))
    store = IncidentStore(tmp_path)
    events = store.replay()
    assert [e["id"] for e in events] == [str(i) for i in range(1, 21)]
    for iid in ("left", "right"):
        assert [e["sequence"] for e in store.replay(investigation_id=iid)] == list(range(1, 11))
    assert len(store.replay("10")) == 10
    assert "sensitive-value" not in json.dumps(events)
    assert all(e["data"]["password"] == "[REDACTED]" for e in events)


def test_incident_list_ignores_task_and_run_records(tmp_path):
    store = IncidentStore(tmp_path)
    item = store.create("/target", "Failure")
    atomic_json(tmp_path / "task-a.json", {"repository": "/target"})
    atomic_json(tmp_path / "run-a.json", {"status": "RUNNING"})
    assert store.list() == [item]


def test_http_history_replay_and_cross_origin_rejected(tmp_path):
    api = WorkspaceAPI(tmp_path)
    item = api.store.create("/target", "Failure")
    event = api.store._emit("tool.started", {"tool": "read_logs"}, item["id"])
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler(Path("ui/workspace")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    try:
        detail = json.load(urllib.request.urlopen(base + "/api/incidents/" + item["id"]))
        assert detail["events"][-1]["id"] == event["id"]
        request = urllib.request.Request(base + "/api/events?investigation_id=" + item["id"],
                                         headers={"Last-Event-ID": "1"})
        with urllib.request.urlopen(request, timeout=3) as response:
            received = []
            while len(received) < 2:
                line = response.readline().decode()
                if line.startswith("data:"):
                    received.append(json.loads(line[5:]))
            assert received[-1]["id"] == event["id"]
        bad = urllib.request.Request(base + "/api/pause", data=b"incident_id=x", headers={"Origin": "https://evil.example"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(bad)
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_graph_public_events_omit_transcripts_and_arguments(active, monkeypatch, tmp_path):
    configure_tools(monkeypatch)
    investigate_graph(active, task(active), GraphProvider(graph_replies(active)),
                      progress=WorkspaceProgress(tmp_path, "incident1"))
    events = IncidentStore(tmp_path).replay()
    types = {e["type"] for e in events}
    assert {"tool.started", "tool.completed", "evidence.added", "hypothesis.updated", "auditor.verdict", "report.ready"} <= types
    assert all(e["investigation_id"] == "incident1" for e in events)
    assert not any("transcript" in e["data"] or "arguments" in e["data"] for e in events)


def test_stale_approval_is_rejected_before_execution(tmp_path):
    api = WorkspaceAPI(tmp_path)
    item = api.store.create("/target", "Failure")
    api.active_runs.update(item["id"], status="AWAITING_APPROVAL", patch="patch bytes")
    with pytest.raises(ValueError, match="Patch changed"):
        api.approval(item["id"], {"patch_hash": "stale", "approved_by": "Tester"}, True)


def test_stop_paused_without_worker_is_terminal(tmp_path):
    api = WorkspaceAPI(tmp_path)
    item = api.store.create("/target", "Failure")
    session = tmp_path / "session"
    session.mkdir()
    api.active_runs.update(item["id"], status="PAUSED", session=str(session))
    result = api.operator_action("stop", incident_id=item["id"])
    assert result["type"] == "run.stopped"
    assert api.detail(item["id"])["run"]["status"] == "STOPPED"
    with pytest.raises(ValueError, match="Only a paused"):
        api.launch(item["id"], "resume")


def test_stop_during_preparation_is_recorded_without_session(tmp_path):
    api = WorkspaceAPI(tmp_path)
    item = api.store.create("/target", "Failure")
    api.active_runs.update(item["id"], status="STARTING")
    api.operator_action("stop", incident_id=item["id"])
    assert api.active_runs._record(item["id"])["status"] == "STOPPED"
