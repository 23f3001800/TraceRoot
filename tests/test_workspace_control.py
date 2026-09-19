import json

from traceroot.workspace_control import ActiveRuns


class Process:
    pid = 44

    def poll(self):
        return None

    def send_signal(self, _signal):
        self.signalled = True


def test_control_records_operator_intent_and_active_process(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    runs = ActiveRuns(tmp_path)
    runs.register("bug-001", Process(), session, ["investigate"])

    message = runs.control("message", "Check deployment timing.")
    pause = runs.control("pause")
    stop = runs.control("stop")

    assert message["incident_id"] == "bug-001"
    assert pause["kind"] == "pause"
    assert json.loads((session / "operator-control.json").read_text())["state"] == "STOP_REQUESTED"
