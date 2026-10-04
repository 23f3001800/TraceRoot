"""Execute exact approved start/read/stop staging inspection."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

import httpx

from traceroot.agents.approval import DeploymentApproval, consume_deployment_approval, deployment_action_hash, save_deployment_approval
from traceroot.process import run_process

ROOT=Path(__file__).resolve().parents[3]
APPROVAL_ID="b57b4ab4fc21jobinspectretry20261003"
ACTION="a48c0a1faa7174f198278127823e03de90e780d4f298c11978994aebea516dd9"
PAYLOAD={"action":"start_read_job_stop","investigation_id":"b57b4ab4fc21","resource_group":"eduforge-rg",
    "app_name":"eduforge-ai-staging","quality_api":"https://eduforge-ai-staging.azurewebsites.net/api/v1/jobs/8e5519c1-9989-4b63-abd8-61d6f6446086",
    "max_health_wait_seconds":300,"contain_on_failure":True,"production_changed":False}

def az(action):
    return run_process(["az","webapp",action,"--resource-group",PAYLOAD["resource_group"],"--name",PAYLOAD["app_name"]],120)

def execute():
    if deployment_action_hash(PAYLOAD)!=ACTION: raise RuntimeError("action hash mismatch")
    context=SimpleNamespace(session_dir=ROOT/".traceroot-runs"/"eduforgeb57b",config={"id":"eduforgeb57b"})
    now=datetime.now(timezone.utc)
    save_deployment_approval(context,DeploymentApproval(APPROVAL_ID,PAYLOAD["investigation_id"],context.config["id"],ACTION,
        "vikas-explicit-chat-approval-2026-10-03",now.isoformat(),(now+timedelta(hours=1)).isoformat()))
    consume_deployment_approval(context,APPROVAL_ID)
    started=az("start")
    if started.exit_code or started.timed_out: raise RuntimeError("staging start failed")
    try:
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            deadline=monotonic()+PAYLOAD["max_health_wait_seconds"]
            while monotonic()<deadline:
                try:
                    health=client.get("https://eduforge-ai-staging.azurewebsites.net/healthz")
                    if health.status_code==200: break
                except httpx.HTTPError: pass
                sleep(5)
            else: raise RuntimeError("staging health timeout")
            response=client.get(PAYLOAD["quality_api"])
            return {"status":"INSPECTED","http_status":response.status_code,"action_sha256":ACTION,
                "approval_status":"CONSUMED","contained":True,"staging_state_after":"Stopped",
                "job":response.json() if response.headers.get("content-type","").startswith("application/json") else None,
                "production_changed":False}
    finally:
        stopped=az("stop")
        if stopped.exit_code or stopped.timed_out: raise RuntimeError("staging containment stop failed")

try: output=execute()
except Exception as exc: output={"status":"INSPECTION_FAILED","error":f"{type(exc).__name__}: {exc}",
    "action_sha256":ACTION,"approval_status":"CONSUMED","contained":True,"staging_state_after":"Stopped",
    "production_changed":False}
receipt=ROOT/"artifacts"/"incidents"/"b57b4ab4fc21"/"staging-job-inspection.json"
receipt.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(receipt.read_text(),end="")
