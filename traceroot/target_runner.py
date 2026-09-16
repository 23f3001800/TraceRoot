from abc import ABC, abstractmethod
from pathlib import Path
from .contracts import ToolError, ToolResult, bounded_int
from .execution import execute_tests
from .process import run_process
class TargetRunner(ABC):
 @abstractmethod
 def run_tests(self,args,timeout): pass
 def run_reproduction(self,args,timeout): return self.run_tests(args,timeout)
 @abstractmethod
 def get_logs(self): pass
 @abstractmethod
 def reset_target(self): pass
class DockerRunner(TargetRunner):
 def __init__(self,context): self.context=context
 def run_tests(self,args,timeout): return execute_tests(self.context,args,timeout)
 def get_logs(self): return []
 def reset_target(self): return ToolResult('rejected',error=ToolError('reset_not_permitted','Runner reset is operator-owned.'))
class LocalRunner(TargetRunner):
 def __init__(self,context): self.context=context
 def run_tests(self,args,timeout):
  bounded_int(timeout,1,120,'timeout'); result=run_process(['python','-m','pytest','-q',*args],timeout,limit=131072,cwd=Path(self.context.repository.source))
  data={'command':['python','-m','pytest','-q',*args],'exit_code':result.exit_code,'stdout':result.stdout.decode(errors='replace')[:65536],'stderr':result.stderr.decode(errors='replace')[:65536],'duration_ms':result.duration_ms,'passed':None,'failed':None,'skipped':None,'errors':None,'collected':None,'failing_tests':[],'http_observations':[],'outcome':'passed' if result.exit_code==0 else 'failed','stdout_truncated':result.stdout_truncated,'stderr_truncated':result.stderr_truncated}
  return ToolResult('timeout',data,ToolError('execution_timeout','Execution exceeded its deadline.')) if result.timed_out else ToolResult('ok',data)
 def get_logs(self): return []
 def reset_target(self): return ToolResult('rejected',error=ToolError('reset_not_permitted','Local reset is operator-owned.'))
def runner_for(context): return DockerRunner(context) if context.config.get('runner', 'docker')=='docker' else LocalRunner(context)
