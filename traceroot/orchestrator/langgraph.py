"""Native LangGraph orchestration adapter."""
from __future__ import annotations


def run(context, task, provider, *, progress, resume_run_id=None):
    from ..agents.langgraph import investigate_graph
    return investigate_graph(
        context, task, provider, progress=progress, resume_run_id=resume_run_id
    )
