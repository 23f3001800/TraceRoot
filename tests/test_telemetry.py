from traceroot import telemetry

def test_telemetry_is_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    telemetry._configured = False
    assert telemetry.configure_telemetry() is False
    with telemetry.span("unit") as current:
        assert current is None or hasattr(current, "is_recording")
