"""Selectable orchestration engines over TraceRoot's bounded investigation core."""
from __future__ import annotations

from importlib.util import find_spec
from typing import Any, Callable

ORCHESTRATORS = {
    "langgraph": {"label": "LangGraph", "package": "langgraph", "default": True},
    "crewai": {"label": "CrewAI", "package": "crewai", "default": False},
    "autogen": {"label": "AutoGen", "package": "autogen_core", "default": False},
}


def validate_orchestrator(name: str | None) -> str:
    value = (name or "langgraph").strip().lower()
    if value not in ORCHESTRATORS:
        raise ValueError("Orchestrator must be langgraph, crewai, or autogen.")
    return value


def capabilities() -> list[dict[str, Any]]:
    return [
        {"id": name, **metadata, "available": find_spec(metadata["package"]) is not None}
        for name, metadata in ORCHESTRATORS.items()
    ]


def _runners() -> dict[str, Callable[..., dict[str, Any]]]:
    from .autogen import run as autogen
    from .crewai import run as crewai
    from .langgraph import run as langgraph
    return {"langgraph": langgraph, "crewai": crewai, "autogen": autogen}


def run_investigation(name, context, task, provider, *, progress, resume_run_id=None):
    selected = validate_orchestrator(name)
    return _runners()[selected](
        context, task, provider, progress=progress, resume_run_id=resume_run_id
    )
