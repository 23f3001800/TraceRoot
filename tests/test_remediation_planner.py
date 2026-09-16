from traceroot.agents.remediation_planner import planner_request, plan_remediation
from traceroot.llms.provider import ModelReply
from test_langgraph import final_report
class Provider:
 def generate(self,*args):
  return ModelReply({"status":"PROPOSAL_READY","root_cause_summary":"Configured destination differs.","proposed_changes":[{"file":"app/main.py","change":"Align destination.","reason":"Matches supported evidence."}],"validation_plan":["Run reproduction."],"risk":"low","risk_reasons":["Source-only change."],"requires_human_approval":True,"limitations":[]},{"input_tokens":1,"output_tokens":1,"thinking_tokens":0})
def test_requires_supported_root_cause():
 r=final_report(); r["status"]="INSUFFICIENT_EVIDENCE"
 try: planner_request(r); assert False
 except ValueError: pass
def test_planner_is_proposal_only():
 result=plan_remediation(Provider(), final_report() | {"status":"ROOT_CAUSE_SUPPORTED"})
 assert result["plan"]["requires_human_approval"]
