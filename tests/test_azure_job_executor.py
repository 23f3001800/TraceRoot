import json
from datetime import datetime, timedelta, timezone
from traceroot.agents.approval import DeploymentApproval, deployment_action_hash, save_deployment_approval
from traceroot.agents.azure_job_executor import AzureJobRequest, action_payload, execute_approved_job
from traceroot.process import ProcessResult

def result(data): return ProcessResult(0, json.dumps(data).encode(), b"", 1, False, False, False)

def test_executes_exact_approved_staging_job(context):
    request = AzureJobRequest("incident1","approve1","trace-rg","repair-staging","sha256:"+"a"*64,
        ("python","-m","traceroot.repair"), {"status":"FIX_VERIFIED"}, 30)
    now = datetime.now(timezone.utc)
    save_deployment_approval(context, DeploymentApproval("approve1","incident1",context.config["id"],
        deployment_action_hash(action_payload(request)),"operator",now.isoformat(),(now+timedelta(hours=1)).isoformat()))
    calls = []
    def runner(argv, timeout):
        calls.append(argv)
        return result({"name":"repair-staging-abc"} if "start" in argv else {"properties":{"status":"Succeeded"}})
    receipt = execute_approved_job(context, request, runner=runner, wait=lambda _:None)
    assert receipt["status"] == "JOB_SUCCEEDED" and receipt["production_changed"] is False
    assert calls[0][:4] == ["az","containerapp","job","start"]
