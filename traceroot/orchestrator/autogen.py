"""AutoGen typed-message adapter preserving TraceRoot's bounded core."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class InvestigationMessage:
    task: dict[str, Any] | None
    resume_run_id: str | None


@dataclass
class InvestigationResult:
    value: dict[str, Any]


def run(context, task, provider, *, progress, resume_run_id=None):
    try:
        from autogen_core import AgentId, RoutedAgent, SingleThreadedAgentRuntime, message_handler
    except ImportError as exc:
        raise ValueError("AutoGen is selected but its optional package is not installed.") from exc

    from .langgraph import run as run_bounded_core

    class TraceRootCoordinator(RoutedAgent):
        def __init__(self):
            super().__init__("TraceRoot bounded investigation coordinator")

        @message_handler
        async def investigate(self, message: InvestigationMessage, ctx: Any) -> InvestigationResult:
            value = await asyncio.to_thread(
                run_bounded_core,
                context,
                message.task,
                provider,
                progress=progress,
                resume_run_id=message.resume_run_id,
            )
            return InvestigationResult(value)

    async def execute() -> dict[str, Any]:
        runtime = SingleThreadedAgentRuntime()
        await TraceRootCoordinator.register(runtime, "traceroot_coordinator", TraceRootCoordinator)
        runtime.start()
        try:
            result = await runtime.send_message(
                InvestigationMessage(task, resume_run_id),
                AgentId("traceroot_coordinator", "default"),
            )
            return result.value
        finally:
            await runtime.stop()

    return asyncio.run(execute())
