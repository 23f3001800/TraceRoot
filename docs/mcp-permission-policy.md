# MCP Permission Policy

TraceRoot uses MCP as a connectivity layer below the Investigator and Evidence Auditor. MCP is not an agent.

## Current mode

`MCP_ACCESS_MODE = "read_only"` is explicit in [traceroot/mcp_policy.py](../traceroot/mcp_policy.py).

Allowed families are `git.*`, `runtime.*`, and `database.*`, for evidence collection only. Denied operations include patch application, commit, push, delete, update, insert, restart, and deploy.

## Why

Investigation needs evidence without changing a target. Writes remain exclusively in the separate remediation boundary:

1. supported root cause;
2. proposal;
3. exact human approval;
4. deterministic policy validation;
5. disposable Docker execution;
6. deterministic verification.

MCP write access is not enabled. Any future write capability needs its own approval, sandbox, and verifier boundary.
