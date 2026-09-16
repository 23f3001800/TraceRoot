from ..contracts import ToolResult, tool
from ..selection import select
from ..target_runner import runner_for

@tool
def run_tests(context, repository: str, test_selector: str | None = None,
              timeout: int = 60, marker: str | None = None) -> ToolResult:
    context.repository.validate(repository)
    return runner_for(context).run_tests(select(context.repository, test_selector, marker), timeout)
