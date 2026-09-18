from traceroot.mcp_policy import MCP_ACCESS_MODE, is_read_only_tool

def test_mcp_policy_is_explicitly_read_only():
    assert MCP_ACCESS_MODE == "read_only"
    assert is_read_only_tool("git.history")
    assert is_read_only_tool("runtime.logs")
    assert is_read_only_tool("database.schema")
    assert not is_read_only_tool("git.push")
    assert not is_read_only_tool("runtime.restart")
