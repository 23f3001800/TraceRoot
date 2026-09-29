import pytest

from traceroot import orchestrator as orchestrators
from traceroot.orchestrator import autogen, crewai


def test_validates_supported_orchestrators():
    assert orchestrators.validate_orchestrator(None) == "langgraph"
    assert orchestrators.validate_orchestrator(" CrewAI ") == "crewai"
    with pytest.raises(ValueError, match="langgraph, crewai, or autogen"):
        orchestrators.validate_orchestrator("other")


def test_capabilities_are_explicit_and_langgraph_is_default():
    items = {item["id"]: item for item in orchestrators.capabilities()}
    assert set(items) == {"langgraph", "crewai", "autogen"}
    assert items["langgraph"]["default"] is True
    assert all(isinstance(item["available"], bool) for item in items.values())


def test_selected_runner_is_used_without_silent_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(crewai, "run", lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True})
    monkeypatch.setattr(orchestrators, "_runners", lambda: {"langgraph": None, "crewai": crewai.run, "autogen": None})
    result = orchestrators.run_investigation(
        "crewai", "context", {"task": True}, "provider", progress="progress"
    )
    assert result == {"ok": True}
    assert calls[0][0] == ("context", {"task": True}, "provider")
    assert calls[0][1]["progress"] == "progress"


@pytest.mark.parametrize("module", [crewai, autogen])
def test_optional_backend_runs_the_bounded_core(monkeypatch, module):
    from traceroot.orchestrator import langgraph
    monkeypatch.setattr(langgraph, "run", lambda *args, **kwargs: {"backend": "ok"})
    assert module.run(None, None, None, progress=None) == {"backend": "ok"}
