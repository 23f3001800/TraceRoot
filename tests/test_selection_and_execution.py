import sys
import pytest
from traceroot.contracts import ToolFailure
from traceroot.selection import reproduction_args, select
from traceroot.process import run_process
from traceroot.tools import run_reproduction, run_tests

def test_automatic_reproduction_uses_public_marker(context):
    args, reason = reproduction_args(context.repository, None)
    assert args == ["tests/test_api.py::test_public_case"]
    assert "public" in reason

def test_named_test_and_filter(context):
    assert select(context.repository, "test_normal") == ["tests/test_api.py::test_normal"]
    assert select(context.repository, None, "not regression") == ["tests", "-m", "not regression"]

@pytest.mark.parametrize("command", [
    ["bash", "-c", "anything"], ["python", "-c", "anything"],
    ["pytest", "benchmarks/bug-001/reproduce.py"], ["pytest", "--override-ini", "x=y"],
    ["pytest", "tests/test_api.py; rm -rf /"], "pytest tests/test_api.py",
    ["pytest", "-p", "evil"], ["pytest", "--rootdir=/"],
])
def test_commands_are_not_shell(context, command):
    result = run_reproduction(context, context.repository.source, command)
    assert result.status == "rejected"

def test_missing_environment_is_not_success(context):
    result = run_reproduction(context, context.repository.source)
    assert result.status == "unavailable"
    assert result.data is None

def test_no_reproduction_is_explicit(context):
    context.repository.manifest = {k: v for k, v in context.repository.manifest.items() if not k.startswith("tests/")}
    result = run_reproduction(context, context.repository.source)
    assert result.status == "unavailable"
    assert result.error.code == "reproduction_unavailable"

def test_setup_failure_not_reproduced(context, monkeypatch):
    import traceroot.tools.reproduction as module
    from traceroot.contracts import ToolResult, ToolError
    monkeypatch.setattr(module, "execute_tests", lambda *args: ToolResult(
        "error", {"exit_code": 1, "failed": 0, "errors": 1, "http_observations": []},
        ToolError("test_execution_error", "setup failed")))
    result = run_reproduction(context, context.repository.source)
    assert result.status == "error" and result.data["reproduced"] is None

def test_http_observation_is_evidence_not_exit_code(context, monkeypatch):
    import traceroot.tools.reproduction as module
    from traceroot.contracts import ToolResult
    monkeypatch.setattr(module, "execute_tests", lambda *args: ToolResult(
        "ok", {"exit_code": 1, "failed": 1, "errors": 0,
               "http_observations": [{"expected": 204, "observed": 503}]}))
    result = run_reproduction(context, context.repository.source)
    assert result.data["reproduced"] is True
    assert result.data["expected"] == 204 and result.data["observed"] == 503

def test_subprocess_timeout_and_output_bound():
    result = run_process([sys.executable, "-c", "import time; print('ready',flush=True); time.sleep(10)"], 1)
    assert result.timed_out and result.duration_ms < 5000 and b"ready" in result.stdout
    result = run_process([sys.executable, "-c", "print('x'*20000)"], 3, limit=512)
    assert result.exit_code == 0 and len(result.stdout) == 512 and result.stdout_truncated

def test_timeout_removes_container(context, monkeypatch):
    import traceroot.execution as module
    from traceroot.process import ProcessResult
    context.config.update(active=True, image="image", db="db", network="network")
    calls = []
    monkeypatch.setattr(module, "checked", lambda *args, **kw: None)
    def fake_docker(ctx, args, *other, **kw):
        calls.append(args)
        return ProcessResult(-9 if args[0] == "start" else 0, b"", b"", 1000, args[0] == "start", False, False)
    monkeypatch.setattr(module, "docker", fake_docker)
    result = module.execute_tests(context, ["tests"], 1)
    assert result.status == "timeout"
    assert any(call[:2] == ["rm", "-f"] for call in calls)


def test_skipped_reproduction_is_not_success(context, monkeypatch):
    import json
    import traceroot.execution as execution
    from traceroot.process import ProcessResult
    context.config.update(active=True, image="image", db="db", network="network")
    report = {"exit_code": 0, "collected": 1, "passed": 0, "failed": 0, "skipped": 1,
              "errors": 0, "records": [], "logs": []}
    monkeypatch.setattr(execution, "checked", lambda *args, **kw: None)
    def fake_docker(ctx, args, *rest, **kwargs):
        output = ("TRACEROOT_REPORT_V1=" + json.dumps(report)).encode() if args[0] == "start" else b""
        return ProcessResult(0, output, b"", 1, False, False, False)
    monkeypatch.setattr(execution, "docker", fake_docker)
    result = run_reproduction(context, context.repository.source)
    assert result.status == "unavailable" and result.data["reproduced"] is None
    assert result.error.code == "tests_not_exercised"
