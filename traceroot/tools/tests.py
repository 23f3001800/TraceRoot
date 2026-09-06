from ..contracts import ToolResult, tool
from ..selection import select
from ..execution import execute_tests

@tool
def run_tests(context, repository: str, test_selector: str | None = None,
              timeout: int = 60, marker: str | None = None) -> ToolResult:
    context.repository.validate(repository)
    return execute_tests(context, select(context.repository, test_selector, marker), timeout)
