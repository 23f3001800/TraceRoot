from ..contracts import ToolResult, tool
from ..selection import reproduction_args
from ..target_runner import runner_for
from ..execution import execute_tests


def _summary(result):
    data = result.data or {}
    return {key: data.get(key) for key in ("exit_code", "outcome", "passed", "failed", "errors", "http_observations")}

@tool
def run_reproduction(context, repository_path: str,
                     reproduction_command: list[str] | None = None,
                     timeout: int = 60, consistency_attempts: int = 1) -> ToolResult:
    context.repository.validate(repository_path)
    if type(consistency_attempts) is not int or not 1 <= consistency_attempts <= 3:
        raise ValueError("consistency_attempts must be between 1 and 3")
    args, reason = reproduction_args(context.repository, reproduction_command)
    attempts = [(runner_for(context).run_reproduction(args, timeout) if context.config.get('runner') else execute_tests(context, args, timeout)) for _ in range(consistency_attempts)]
    result = attempts[-1]
    if result.data is not None:
        result.data["selection_reason"] = reason
        result.data["exact_inputs"] = {"test_command": args, "requested_command": reproduction_command, "timeout_seconds": timeout}
        result.data["consistency_attempts"] = consistency_attempts
        result.data["attempt_results"] = [_summary(attempt) for attempt in attempts]
        result.data["consistent"] = None if consistency_attempts == 1 else len({str(_summary(attempt)) for attempt in attempts}) == 1
        result.data["reproduced"] = None
        result.data["expected"] = None
        result.data["observed"] = None
        if result.status == "ok":
            observations = result.data["http_observations"]
            if observations and result.data["failed"] > 0 and result.data["errors"] == 0:
                unique = {(x["expected"], x["observed"]) for x in observations}
                if len(unique) == 1:
                    expected, observed = unique.pop()
                    result.data.update(reproduced=expected != observed, expected=expected, observed=observed)
            elif result.data["failed"] > 0 and result.data["errors"] == 0:
                result.data["reproduced"] = True
            elif result.data["exit_code"] == 0:
                result.data["reproduced"] = False
    return result
