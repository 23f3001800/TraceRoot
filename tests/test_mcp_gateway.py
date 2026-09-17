from traceroot.mcp_gateway import MCPGateway, MCPTool

class Client:
 def list_tools(self):
  return [MCPTool("git","git.history","Read commits.",{"type":"object"}),MCPTool("git","shell.run","Denied.",{})]
 def call_tool(self,name,arguments):
  return {"status":"ok","data":{"name":name,"arguments":arguments}}

def test_discovers_only_read_only_families():
 gateway=MCPGateway({"git":Client()})
 assert [tool["name"] for tool in gateway.discover()] == ["git.history"]

def test_invokes_structured_read_only_tool():
 result=MCPGateway({"git":Client()}).invoke("git","git.history",{"limit":5})
 assert result.status=="ok" and result.data["arguments"]["limit"]==5

def test_denies_non_mcp_family():
 assert MCPGateway({"git":Client()}).invoke("git","shell.run",{}).error.code=="mcp_tool_denied"
