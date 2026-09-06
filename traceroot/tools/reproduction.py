from ..contracts import ToolResult, tool
from ..selection import reproduction_args
from ..execution import execute_tests

@tool
def run_reproduction(context, repository_path: str,
                     reproduction_command: list[str] | None = None,
                     timeout: int = 60) -> ToolResult:
    context.repository.validate(repository_path)
    args, reason = reproduction_args(context.repository, reproduction_command)
    result = execute_tests(context, args, timeout)
    if result.data is not None:
        result.data["selection_reason"] = reason
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
            elif result.data["exit_code"] == 0:
                result.data["reproduced"] = False
    return result
