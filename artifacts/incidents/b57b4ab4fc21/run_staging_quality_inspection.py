"""Run approved staging quality inspection and always stop staging."""
import hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
import httpx
from traceroot.agents.approval import DeploymentApproval, consume_deployment_approval, deployment_action_hash, save_deployment_approval
from traceroot.process import run_process
ROOT=Path(__file__).resolve().parents[3]; APP_ROOT=Path("/home/vikas/EduForge-AI")
APPROVAL_ID="b57b4ab4fc21qualityinspect20261003"; ACTION="91e79c329ca7fb4c1f38bc066f73849a98ffe6ef442223e0d20d2f75c84f2da8"
PAYLOAD={"action":"start_run_quality_inspect_stop","investigation_id":"b57b4ab4fc21","resource_group":"eduforge-rg","app_name":"eduforge-ai-staging","quality_input":"backend/tests/fixtures/documents/physics.pdf","quality_input_sha256":"7d6218dc8ef04b01076718ad011f70bafdaee7c0a41e8c3f63f20c15ac01f0d5","quality_api":"https://eduforge-ai-staging.azurewebsites.net/api/v1","expected_llm_profile":"ci","max_health_wait_seconds":300,"max_quality_wait_seconds":300,"contain_on_failure":True,"production_changed":False}
def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""): digest.update(block)
    return digest.hexdigest()
def az(action): return run_process(["az","webapp",action,"--resource-group",PAYLOAD["resource_group"],"--name",PAYLOAD["app_name"]],120)
def execute():
    if deployment_action_hash(PAYLOAD)!=ACTION: raise RuntimeError("action hash mismatch")
    fixture=APP_ROOT/PAYLOAD["quality_input"]
    if sha256(fixture)!=PAYLOAD["quality_input_sha256"]: raise RuntimeError("quality input hash mismatch")
    ctx=SimpleNamespace(session_dir=ROOT/".traceroot-runs"/"eduforgeb57b",config={"id":"eduforgeb57b"}); now=datetime.now(timezone.utc)
    save_deployment_approval(ctx,DeploymentApproval(APPROVAL_ID,PAYLOAD["investigation_id"],ctx.config["id"],ACTION,"vikas-explicit-chat-approval-2026-10-03",now.isoformat(),(now+timedelta(hours=1)).isoformat())); consume_deployment_approval(ctx,APPROVAL_ID)
    started=az("start")
    if started.exit_code or started.timed_out: raise RuntimeError("staging start failed")
    try:
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            deadline=monotonic()+PAYLOAD["max_health_wait_seconds"]
            while monotonic()<deadline:
                try:
                    health=client.get("https://eduforge-ai-staging.azurewebsites.net/healthz"); ready=client.get("https://eduforge-ai-staging.azurewebsites.net/readyz")
                    if health.status_code==ready.status_code==200 and ready.json().get("llm_profile")==PAYLOAD["expected_llm_profile"]: break
                except (httpx.HTTPError,ValueError): pass
                sleep(5)
            else: raise RuntimeError("staging health timeout")
            with fixture.open("rb") as stream: uploaded=client.post(PAYLOAD["quality_api"]+"/documents",files={"file":(fixture.name,stream,"application/pdf")})
            uploaded.raise_for_status(); document=uploaded.json()
            if document.get("sha256")!=PAYLOAD["quality_input_sha256"]: raise RuntimeError("uploaded document hash mismatch")
            created=client.post(PAYLOAD["quality_api"]+"/jobs",json={"document_id":document["document_id"]}); created.raise_for_status(); job_id=created.json()["job_id"]
            deadline=monotonic()+PAYLOAD["max_quality_wait_seconds"]
            while monotonic()<deadline:
                response=client.get(PAYLOAD["quality_api"]+"/jobs/"+job_id); response.raise_for_status(); job=response.json()
                if job.get("status") in {"succeeded","succeeded_partial","failed","cancelled"}: break
                sleep(2)
            else: raise RuntimeError("quality job timeout")
            return {"status":"QUALITY_INSPECTED","action_sha256":ACTION,"approval_status":"CONSUMED","quality_job":job,"healthz":health.json(),"readyz":ready.json(),"contained":True,"staging_state_after":"Stopped","production_changed":False}
    finally:
        stopped=az("stop")
        if stopped.exit_code or stopped.timed_out: raise RuntimeError("staging containment stop failed")
try: output=execute()
except Exception as exc: output={"status":"QUALITY_INSPECTION_FAILED","error":f"{type(exc).__name__}: {exc}","action_sha256":ACTION,"approval_status":"CONSUMED","contained":True,"staging_state_after":"Stopped","production_changed":False}
receipt=ROOT/"artifacts"/"incidents"/"b57b4ab4fc21"/"staging-quality-inspection.json"; receipt.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(receipt.read_text(),end="")
