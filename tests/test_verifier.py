from traceroot.agents.verifier import verify_remediation
from traceroot.contracts import ToolResult
class Runner:
 def __init__(self,a,b): self.a,self.b=a,b
 def run_reproduction(self,*x): return self.a
 def run_tests(self,*x): return self.b
def result(status="ok",outcome="passed",failed=0,exit_code=0,reproduced=False): return ToolResult(status,{"outcome":outcome,"failed":failed,"exit_code":exit_code,"reproduced":reproduced})
def check(monkeypatch,context,a,b):
 context.config["runner"]="docker"
 import traceroot.agents.verifier as module
 monkeypatch.setattr(module,"DockerRunner",lambda c:Runner(a,b))
 return verify_remediation(context,["repro"],["regression"])
def test_fix_verified(monkeypatch,context): assert check(monkeypatch,context,result(),result())["status"]=="FIX_VERIFIED"
def test_reproduction_still_fails(monkeypatch,context): assert check(monkeypatch,context,result(outcome="failed",failed=1,reproduced=True),result())["status"]=="REPRODUCTION_STILL_FAILS"
def test_regression_introduced(monkeypatch,context): assert check(monkeypatch,context,result(),result(outcome="failed",failed=1,exit_code=1))["status"]=="REGRESSION_INTRODUCED"
def test_tool_failure(monkeypatch,context): assert check(monkeypatch,context,result(status="timeout"),result())["status"]=="VERIFICATION_TOOL_FAILURE"
