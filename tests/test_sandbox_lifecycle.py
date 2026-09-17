from traceroot.agents.sandbox_executor import rollback_patch, destroy_sandbox
from traceroot.process import ProcessResult
def test_rollback_restores_base(monkeypatch,context):
 context.config.update(runner="docker",active=True,image="traceroot-investigation:unit-patch-x",base_image="traceroot-investigation:unit",patched_image="traceroot-investigation:unit-patch-x")
 import traceroot.agents.sandbox_executor as m
 monkeypatch.setattr(m,"docker",lambda *a,**k:ProcessResult(0,b"",b"",1,False,False,False))
 assert rollback_patch(context)["status"]=="PATCH_ROLLED_BACK" and context.config["image"]=="traceroot-investigation:unit"
def test_destroy_calls_cleanup_and_removes_image(monkeypatch,context):
 context.config.update(runner="docker",active=True,image="traceroot-investigation:unit")
 import traceroot.agents.sandbox_executor as m
 monkeypatch.setattr(m,"docker",lambda *a,**k:ProcessResult(0,b"",b"",1,False,False,False))
 import traceroot.docker_runtime as d
 monkeypatch.setattr(d,"cleanup",lambda c:None)
 assert destroy_sandbox(context)["status"]=="SANDBOX_DESTROYED"
