import json
from uuid import uuid4
from .contracts import ToolError, ToolFailure, ToolResult, bounded_int, utc_now
from .docker_runtime import app_url, checked, container_options, docker, require_active

def execute_tests(context, args: list[str], timeout: int) -> ToolResult:
    bounded_int(timeout, 1, 120, "timeout")
    require_active(context)
    for path in context.repository.manifest:
        context.repository.read(path)
    run_id = uuid4().hex
    name = f"traceroot-test-{run_id[:12]}"
    argv = ["python", "-m", "pytest", "-p", "reporter", "-p", "no:cacheprovider",
            "-c", "/opt/traceroot/pytest.ini", "--rootdir=/repo", "-q", "--tb=short", "--show-capture=no", *args]
    start = utc_now()
    data = {"command": argv, "exit_code": None, "stdout": "", "stderr": "", "duration_ms": 0,
            "passed": None, "failed": None, "skipped": None, "errors": None, "collected": None,
            "http_observations": [], "failing_tests": [], "outcome": "unknown"}
    result = None
    created = False
    try:
        checked(context, ["create", *container_options(context, name),
                          "--env", f"DATABASE_URL={app_url(context)}",
                          context.config["image"], *argv])
        created = True
        process = docker(context, ["start", "-a", name], timeout, limit=2 * 1024 * 1024)
        # Remove secrets from executable/test output before exposing it.
        from .tools.logs import redact
        secrets = [context.config[k] for k in ("app_password", "inspector_password", "admin_password")]
        data.update(exit_code=process.exit_code,
                    stdout=redact(process.stdout[:65536].decode("utf-8", errors="replace"), secrets),
                    stderr=redact(process.stderr[:65536].decode("utf-8", errors="replace"), secrets),
                    duration_ms=process.duration_ms,
                    stdout_truncated=process.stdout_truncated or len(process.stdout) > 65536, stderr_truncated=process.stderr_truncated or len(process.stderr) > 65536)
        if process.timed_out:
            data["outcome"] = "timed_out"
            result = ToolResult("timeout", data, ToolError("execution_timeout", "Execution exceeded its deadline."))
        else:
            lines = process.stdout.decode("utf-8", errors="replace").splitlines()
            reports = [line.removeprefix("TRACEROOT_REPORT_V1=") for line in lines if line.startswith("TRACEROOT_REPORT_V1=")]
            clean = "\n".join(line for line in lines if not line.startswith("TRACEROOT_REPORT_V1="))
            data["stdout"] = redact(clean[:65536], secrets)
            data["stdout_truncated"] = process.stdout_truncated or len(clean.encode()) > 65536
            data["stderr"] = data["stderr"][:65536]
            data["stderr_truncated"] |= len(process.stderr) > 65536
            if len(reports) != 1 or process.stdout_truncated:
                result = ToolResult("error", data, ToolError("report_unavailable", "Execution produced no bounded pytest report."))
            else:
                report = json.loads(reports[0])
                if report["exit_code"] != process.exit_code:
                    raise ToolFailure("report_invalid", "Execution report exit status does not match.", "error")
                for key in ("passed", "failed", "skipped", "errors", "collected"):
                    data[key] = report[key]
                data["failing_tests"] = sorted({r["node_id"] for r in report["records"] if r["outcome"] == "failed"})
                data["http_observations"] = [r["http_observation"] for r in report["records"] if "http_observation" in r]
                context.store_logs(report["logs"], run_id)
                if process.exit_code == 0 and report["passed"] > 0 and not report["errors"] and not report["failed"]:
                    data["outcome"] = "passed"
                    result = ToolResult("ok", data)
                elif process.exit_code == 0:
                    data["outcome"] = "not_exercised"
                    result = ToolResult("unavailable", data, ToolError("tests_not_exercised", "No selected test actually passed or failed."))
                elif process.exit_code == 1 and report["failed"] > 0 and not report["errors"]:
                    data["outcome"] = "failed"
                    result = ToolResult("ok", data)
                else:
                    data["outcome"] = "execution_error"
                    result = ToolResult("error", data, ToolError("test_execution_error", "Tests were not completed normally."))
        result.metadata.update(run_id=run_id, started_at=start, log_source="application",
                               snapshot_id=context.repository.snapshot_id)
        return result
    finally:
        removed = docker(context, ["rm", "-f", name]) if created else None
        if removed is not None and removed.exit_code != 0:
            raise ToolFailure("cleanup_failed", "Execution container could not be removed.", "error")
