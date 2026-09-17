import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from traceroot.agents.approval import TargetCommitApproval, commit_action_hash, load_target_commit_approval, save_target_commit_approval
from traceroot.agents.git_workflow import VerifiedBranchRequest, create_verified_branch_commit
from traceroot.context import Context
from traceroot.contracts import ToolFailure
from traceroot.repository import make_snapshot

PATCH = """diff --git a/app/value.py b/app/value.py
--- a/app/value.py
+++ b/app/value.py
@@ -1 +1 @@
-old
+new
"""

def command(root,*args): return subprocess.run(args,cwd=root,check=True,capture_output=True,text=True)
def repository(tmp_path):
 root=tmp_path/"repo";(root/"app").mkdir(parents=True);(root/"app"/"value.py").write_text("old\n")
 command(root,"git","init","-q");command(root,"git","config","user.email","trace@example.test");command(root,"git","config","user.name","TraceRoot Test")
 command(root,"git","add","app/value.py");command(root,"git","commit","-qm","Create initial verification fixture");return root
def context_for(tmp_path,root):
 session=tmp_path/"session";session.mkdir();snapshot=session/"snapshot";snapshot.mkdir()
 return Context({"id":"unit","repository":str(root),"snapshot":str(snapshot),"manifest":{}},session)
def request(root,status="FIX_VERIFIED",approval_id="commit1"):
 return VerifiedBranchRequest("bug-003-e2e",str(root),PATCH,{"status":status},"traceroot/bug-003-idempotency","Fix repeated order idempotency handling",approval_id)
def approve(context,req):
 now=datetime.now(timezone.utc)
 save_target_commit_approval(context,TargetCommitApproval(req.approval_id,req.investigation_id,str(Path(req.repository).resolve()),context.config["id"],commit_action_hash(req.repository,req.patch,req.branch,req.commit_message,req.verification),"human",now.isoformat(),(now+timedelta(hours=1)).isoformat()))
def test_creates_approved_target_branch_commit(tmp_path):
 root=repository(tmp_path);context=context_for(tmp_path,root);req=request(root);approve(context,req)
 result=create_verified_branch_commit(context,req)
 assert result["status"]=="BRANCH_COMMITTED" and result["published"] is False
 assert (root/"app"/"value.py").read_text()=="new\n"
 assert load_target_commit_approval(context,"commit1").status=="CONSUMED"
def test_requires_target_commit_approval(tmp_path):
 root=repository(tmp_path);context=context_for(tmp_path,root)
 with pytest.raises(ToolFailure) as error:create_verified_branch_commit(context,request(root))
 assert error.value.code=="approval_unknown"
