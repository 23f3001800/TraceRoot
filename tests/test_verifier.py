from traceroot.agents.verifier import verify_remediation
from traceroot.contracts import ToolResult
class Runner:
 def __init__(self,a,b): self.a,self.b=a,b
 def run_reproduction(self,*x): return self.a
 def run_tests(self,*x): return self.b
def result(status="ok",outcome="passed",failed=0,exit_code=0,reproduced=False,passed=1,errors=0): return ToolResult(status,{"outcome":outcome,"failed":failed,"exit_code":exit_code,"reproduced":reproduced,"passed":passed,"errors":errors})
def check(monkeypatch,context,a,b):
 context.config["runner"]="docker"
 import traceroot.agents.verifier as module
 monkeypatch.setattr(module,"DockerRunner",lambda c:Runner(a,b))
 return verify_remediation(context,["repro"],["regression"])
def test_fix_verified(monkeypatch,context): assert check(monkeypatch,context,result(),result())["status"]=="FIX_VERIFIED"
def test_reproduction_still_fails(monkeypatch,context): assert check(monkeypatch,context,result(outcome="failed",failed=1,reproduced=True),result())["status"]=="REPRODUCTION_STILL_FAILS"
def test_regression_introduced(monkeypatch,context): assert check(monkeypatch,context,result(),result(outcome="failed",failed=1,exit_code=1))["status"]=="REGRESSION_INTRODUCED"
def test_tool_failure(monkeypatch,context): assert check(monkeypatch,context,result(status="timeout"),result())["status"]=="VERIFICATION_TOOL_FAILURE"

def test_zero_tests_cannot_verify(monkeypatch,context):
 assert check(monkeypatch,context,result(passed=0),result())["status"]=="INSUFFICIENT_VERIFICATION"
 assert check(monkeypatch,context,result(),result(passed=0))["status"]=="INSUFFICIENT_VERIFICATION"

def test_collection_errors_cannot_verify(monkeypatch,context):
 assert check(monkeypatch,context,result(errors=1),result())["status"]=="INSUFFICIENT_VERIFICATION"

def test_focused_tests_are_recorded(monkeypatch,context):
 context.config["runner"]="docker"
 import traceroot.agents.verifier as module
 monkeypatch.setattr(module,"DockerRunner",lambda c:Runner(result(),result()))
 verified=verify_remediation(context,["repro"],["regression"],focused_args=["focused"])
 assert verified["status"]=="FIX_VERIFIED"
 assert verified["focused"]["data"]["passed"]==1
