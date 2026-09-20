import pytest
from traceroot.agents.state import atomic_json
from traceroot.workspace_metrics import usage_metrics, validate_pricing


def test_cost_is_unavailable_without_configured_rates(tmp_path):
    events = [{"type": "agent.finished", "data": {"model": "example", "duration_ms": 120,
               "usage": {"input_tokens": 100, "output_tokens": 20}}}]
    metrics = usage_metrics(tmp_path, {}, events)
    assert metrics["estimated_cost_usd"] is None
    assert metrics["model_latency_ms"] == 120
    assert metrics["input_tokens"] == 100
    assert metrics["unpriced_models"] == ["example"]


def test_cost_uses_reported_tokens_and_explicit_model_rates(tmp_path):
    rate = validate_pricing({"model": "example", "input_usd_per_million": 2, "output_usd_per_million": 8})
    atomic_json(tmp_path / "pricing.json", {"example": rate})
    events = [{"type": "agent.finished", "data": {"model": "example", "duration_ms": 1000,
               "usage": {"input_tokens": 1000, "output_tokens": 250}}}]
    metrics = usage_metrics(tmp_path, {}, events)
    assert metrics["estimated_cost_usd"] == 0.004
    assert metrics["completed_model_calls"] == 1


@pytest.mark.parametrize("value", ["nan", "inf", -1, "unknown"])
def test_invalid_rates_are_rejected(value):
    with pytest.raises(ValueError):
        validate_pricing({"model": "example", "input_usd_per_million": value, "output_usd_per_million": 1})


def test_legacy_latency_uses_recorded_summary(tmp_path):
    events = [{"type": "agent.finished", "data": {"usage": {"input_tokens": 10, "output_tokens": 2}}}]
    result = usage_metrics(tmp_path, {"summary": {"model": "example", "latency_ms_by_role": {"investigator": 350}}}, events)
    assert result["model_latency_ms"] == 350
