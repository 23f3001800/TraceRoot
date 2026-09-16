from traceroot.agents.sandbox_executor import ExecutionRequest, validate_execution_request
from traceroot.contracts import ToolFailure

def test_executor_requires_docker_and_approval(context):
    request=ExecutionRequest("", context.repository.source, "diff --git a/app/main.py b/app/main.py\n", {})
    try: validate_execution_request(context, request); assert False
    except ToolFailure as error: assert error.code == "docker_required"

def test_local_target_is_never_execution_enabled(context):
    context.config["runner"]="docker"; context.config["active"]=True
    request=ExecutionRequest("approval-1", context.repository.source, "invalid", {})
    try: validate_execution_request(context, request); assert False
    except ToolFailure as error: assert error.code == "invalid_patch"
