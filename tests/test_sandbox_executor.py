from datetime import datetime, timedelta, timezone
from traceroot.agents.approval import ApprovalRecord, patch_hash, save_approval
from traceroot.agents.sandbox_executor import ExecutionRequest, validate_execution_request
from traceroot.contracts import ToolFailure
PATCH = '''diff --git a/app/main.py b/app/main.py
--- a/app/main.py
+++ b/app/main.py
@@ -1 +1 @@
-a
+b
'''
def record(context, patch=PATCH, **changes):
 base=dict(approval_id="ok1", investigation_id="run1", approved_patch_hash=patch_hash(patch), repository=context.repository.source, session_id=context.config["id"], approved_by="human", approved_at=datetime.now(timezone.utc).isoformat(), expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
 base.update(changes); save_approval(context, ApprovalRecord(**base)); return ExecutionRequest("ok1", context.repository.source, patch, {})
def denied(context, request, code):
 try: validate_execution_request(context, request); assert False
 except ToolFailure as error: assert error.code == code
def test_missing_approval(context):
 context.config.update(runner="docker",active=True); denied(context,ExecutionRequest("none",context.repository.source,PATCH,{}),"approval_unknown")
def test_exact_patch_and_scope(context):
 context.config.update(runner="docker",active=True); r=record(context); assert validate_execution_request(context,r).approval_id=="ok1"; denied(context,ExecutionRequest("ok1",context.repository.source,PATCH+"+x",{}),"approval_patch_mismatch")
def test_expired_and_consumed(context):
 context.config.update(runner="docker",active=True); denied(context,record(context,expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()),"approval_invalid")
def test_local_and_foreign(context):
 denied(context,record(context),"docker_required"); context.config.update(runner="docker",active=True); denied(context,ExecutionRequest("ok1","/tmp/foreign",PATCH,{}),"approval_scope_mismatch")
def test_policy_rejections(context):
 context.config.update(runner="docker",active=True)
 binary_patch = "diff --git a/a b/a" + chr(10) + "GIT binary patch"
 for patch in ("bad", "diff --git a/../x b/../x", "diff --git a/benchmarks/x b/benchmarks/x", binary_patch):
  denied(context,ExecutionRequest("none",context.repository.source,patch,{}),"invalid_patch" if patch=="bad" else "patch_policy_denied")
