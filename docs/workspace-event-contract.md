# Workspace event contract

The loopback workspace uses Server-Sent Events (SSE) for concise, server-to-browser investigation updates. It uses normal HTTP POST requests for operator actions. It does not expose model chain-of-thought.

## Current events

- `workspace.ready`
- `incident.reported`
- `run.message`
- `run.pause_requested`
- `run.resume_requested`

## Graph event vocabulary

When the incident controller is connected, it will emit these concise state events:

- `run.started`, `stage.changed`, `run.paused`, `run.resumed`, `run.completed`
- `agent.started`, `agent.message`, `agent.finished`
- `tool.started`, `tool.completed`, `tool.failed`
- `hypothesis.created`, `hypothesis.updated`, `evidence.added`
- `auditor.started`, `auditor.verdict`
- `remediation.proposed`, `approval.requested`, `approval.received`
- `patch.ready`, `patch.applied`, `verification.started`, `verification.result`
- `provider.error`

Each event includes an ID, UTC timestamp, type, and bounded public data. Events may describe an action, observation, result, or required user decision; they must never include hidden reasoning, secrets, or full sensitive prompts.

## Live graph event bridge

Use `--workspace-dir .traceroot-workspace` with `investigate` or `resume` to publish bounded LangGraph progress into the local SSE timeline. The bridge translates graph transitions, tool events, and provider failures into concise public event types; it does not pass prompts, tool arguments, secrets, or private reasoning.

Verification: workspace bridge plus LangGraph focused tests passed, 13 tests total.
