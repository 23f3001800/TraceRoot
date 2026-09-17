from datetime import datetime, timedelta, timezone
from traceroot.agents.approval import ApprovalRecord, patch_hash, save_approval, load_approval
from traceroot.agents.sandbox_executor import ExecutionRequest, execute_approved_patch
from traceroot.process import ProcessResult
PATCH = "diff --git a/app/main.py b/app/main.py" + chr(10) + "--- a/app/main.py" + chr(10) + "+++ b/app/main.py" + chr(10) + "@@ -1 +1 @@" + chr(10) + "-a" + chr(10) + "+b" + chr(10)
def test_apply_consumes_exact_approval(monkeypatch,context):
 context.config.update(runner="docker",active=True,network="net",image="image")
 save_approval(context,ApprovalRecord("a2","i2",patch_hash(PATCH),context.repository.source,context.config["id"],"human",datetime.now(timezone.utc).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
 import traceroot.agents.sandbox_executor as module
 monkeypatch.setattr(module,"docker",lambda *a,**k: ProcessResult(0,b"",b"",1,False,False,False))
 result=execute_approved_patch(context,ExecutionRequest("a2",context.repository.source,PATCH,{}))
 assert result["status"]=="PATCH_APPLIED" and load_approval(context,"a2").status=="CONSUMED" and context.config["image"].startswith("image-patch-")
