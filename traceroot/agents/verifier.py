"""Deterministic verifier for a future sandbox executor."""
from __future__ import annotations
from ..target_runner import DockerRunner

def verification_plan(context, reproduction_args: list[str], regression_args: list[str], timeout: int = 120) -> dict:
    if context.config.get("runner") != "docker":
        raise ValueError("Verification requires DockerRunner.")
    runner = DockerRunner(context)
    return {"reproduction": runner.run_reproduction(reproduction_args, timeout).to_dict(),
            "regression": runner.run_tests(regression_args, timeout).to_dict()}
