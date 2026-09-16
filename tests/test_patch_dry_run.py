from traceroot.agents.sandbox_executor import ExecutionRequest, docker_apply_check
from traceroot.agents.approval import ApprovalRecord, patch_hash, save_approval
from traceroot.process import ProcessResult
from datetime import datetime, timedelta, timezone
PATCH = "diff --git a/app/main.py b/app/main.py" + chr(10) + "--- a/app/main.py" + chr(10) + "+++ b/app/main.py" + chr(10) + "@@ -1 +1 @@" + chr(10) + "-a" + chr(10) + "+b" + chr(10)
def request(context):
 context.config.update(runner="docker",active=True,network="net",image="image")
 record=ApprovalRecord("a1","i1",patch_hash(PATCH),context.repository.source,context.config["id"],"human",datetime.now(timezone.utc).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
 save_approval(context,record); return ExecutionRequest("a1",context.repository.source,PATCH,{})
def test_docker_dry_check(monkeypatch,context):
 import traceroot.agents.sandbox_executor as module
 monkeypatch.setattr(module,"docker",lambda *a,**k:ProcessResult(0,b"",b"",1,False,False,False))
 assert docker_apply_check(context,request(context))["status"]=="PATCH_CHECKED"
def test_dry_check_rejection(monkeypatch,context):
 import traceroot.agents.sandbox_executor as module
 monkeypatch.setattr(module,"docker",lambda *a,**k:ProcessResult(1,b"",b"",1,False,False,False))
 from traceroot.contracts import ToolFailure
 try: docker_apply_check(context,request(context)); assert False
 except ToolFailure as error: assert error.code=="patch_rejected"
