"""Deterministic verification boundary; models never grade remediation."""
from __future__ import annotations
from ..target_runner import DockerRunner


def _normal(result: dict) -> bool:
    return result["status"] == "ok" and result.get("data", {}).get("outcome") in {"passed", "failed"}


def _passed(result: dict) -> bool:
    data = result.get("data", {})
    return (_normal(result) and data.get("outcome") == "passed" and data.get("exit_code") == 0
            and data.get("passed", 0) > 0 and not data.get("failed", 0) and not data.get("errors", 0))


def verify_remediation(context, reproduction_args: list[str], regression_args: list[str],
                       timeout: int = 120, *, focused_args: list[str] | None = None) -> dict:
    checks = {"reproduction": None, "focused": None, "regression": None}
    def outcome(status):
        return {"status": status, **checks}
    if context.config.get("runner") != "docker":
        return outcome("VERIFICATION_TOOL_FAILURE")
    runner = DockerRunner(context)
    checks["reproduction"] = runner.run_reproduction(reproduction_args, timeout).to_dict()
    reproduction = checks["reproduction"]
    if not _normal(reproduction):
        return outcome("VERIFICATION_TOOL_FAILURE")
    if reproduction["data"].get("reproduced") is True or reproduction["data"].get("failed", 0):
        return outcome("REPRODUCTION_STILL_FAILS")
    if not _passed(reproduction):
        return outcome("INSUFFICIENT_VERIFICATION")
    if focused_args:
        checks["focused"] = runner.run_tests(focused_args, timeout).to_dict()
        if not _normal(checks["focused"]):
            return outcome("VERIFICATION_TOOL_FAILURE")
        if not _passed(checks["focused"]):
            return outcome("FOCUSED_TESTS_FAILED")
    checks["regression"] = runner.run_tests(regression_args, timeout).to_dict()
    if not _normal(checks["regression"]):
        return outcome("VERIFICATION_TOOL_FAILURE")
    if checks["regression"]["data"].get("failed", 0) or checks["regression"]["data"].get("exit_code") != 0:
        return outcome("REGRESSION_INTRODUCED")
    if not _passed(checks["regression"]):
        return outcome("INSUFFICIENT_VERIFICATION")
    return outcome("FIX_VERIFIED")
