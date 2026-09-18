import json

from traceroot.workspace_ui import IncidentStore


def test_workspace_stores_reports_and_semantic_events(tmp_path):
    store = IncidentStore(tmp_path)

    item = store.create("/tmp/target", "Order creation returns 500", runtime="staging")
    event = store.action("run.message", "Please prioritize runtime logs.")

    assert store.list()[0]["id"] == item["id"]
    assert store.list()[0]["runtime"] == "staging"
    assert event["type"] == "run.message"
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [item["type"] for item in events] == ["incident.reported", "run.message"]
    assert events[0]["data"]["incident"]["id"] == item["id"]


def test_workspace_progress_maps_graph_events_to_semantic_events(tmp_path):
    from traceroot.workspace_ui import WorkspaceProgress

    progress = WorkspaceProgress(tmp_path)
    progress({"event": "graph_transition", "node": "evidence_auditor", "status": "running"})
    progress({"event": "provider_failure", "code": "timeout", "status": "failed"})

    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert events[0]["type"] == "agent.started"
    assert events[0]["data"]["label"] == "Evidence Auditor"
    assert events[1]["type"] == "provider.error"
    assert events[1]["data"]["code"] == "timeout"
