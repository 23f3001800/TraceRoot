import json

from traceroot.workspace_ui import IncidentStore


def test_workspace_stores_reports_and_semantic_events(tmp_path):
    store = IncidentStore(tmp_path)

    item = store.create("/tmp/target", "Order creation returns 500")
    event = store.action("run.message", "Please prioritize runtime logs.")

    assert store.list()[0]["id"] == item["id"]
    assert event["type"] == "run.message"
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [item["type"] for item in events] == ["incident.reported", "run.message"]
    assert events[0]["data"]["incident"]["id"] == item["id"]
