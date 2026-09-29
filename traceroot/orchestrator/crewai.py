"""CrewAI Flow adapter preserving TraceRoot's bounded core and checkpoints."""
from __future__ import annotations


def run(context, task, provider, *, progress, resume_run_id=None):
    try:
        from crewai.flow.flow import Flow, start
    except ImportError as exc:
        raise ValueError("CrewAI is selected but its optional package is not installed.") from exc

    from .langgraph import run as run_bounded_core

    class TraceRootCrewFlow(Flow):
        @start()
        def bounded_investigation(self):
            return run_bounded_core(
                context, task, provider, progress=progress, resume_run_id=resume_run_id
            )

    return TraceRootCrewFlow().kickoff()
