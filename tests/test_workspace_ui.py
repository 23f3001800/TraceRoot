from traceroot.workspace_ui import IncidentStore

def test_persists_reported_incident(tmp_path):
 store=IncidentStore(tmp_path)
 item=store.create("/tmp/target","Orders return 500.","pytest -q tests/test_orders.py")
 assert item["status"]=="REPORTED"
 assert store.list()[0]["id"]==item["id"]
