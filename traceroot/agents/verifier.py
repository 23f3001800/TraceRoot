"""Deterministic verification boundary; models never grade remediation."""
from __future__ import annotations
from ..target_runner import DockerRunner

def _normal(result: dict) -> bool:
    return result["status"] == "ok" and result.get("data", {}).get("outcome") in {"passed", "failed"}

def verify_remediation(context, reproduction_args: list[str], regression_args: list[str], timeout: int = 120) -> dict:
    if context.config.get("runner") != "docker":
        return {"status": "VERIFICATION_TOOL_FAILURE", "reproduction": None, "regression": None}
    runner = DockerRunner(context)
    reproduction = runner.run_reproduction(reproduction_args, timeout).to_dict()
    if not _normal(reproduction):
        return {"status": "VERIFICATION_TOOL_FAILURE", "reproduction": reproduction, "regression": None}
    if reproduction["data"].get("reproduced") is True or reproduction["data"].get("failed", 0):
        return {"status": "REPRODUCTION_STILL_FAILS", "reproduction": reproduction, "regression": None}
    regression = runner.run_tests(regression_args, timeout).to_dict()
    if not _normal(regression):
        return {"status": "VERIFICATION_TOOL_FAILURE", "reproduction": reproduction, "regression": regression}
    if regression["data"].get("failed", 0) or regression["data"].get("exit_code") != 0:
        return {"status": "REGRESSION_INTRODUCED", "reproduction": reproduction, "regression": regression}
    return {"status": "FIX_VERIFIED", "reproduction": reproduction, "regression": regression}
