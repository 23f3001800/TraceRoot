"""Small OpenTelemetry boundary; disabled unless an OTLP endpoint is configured."""
from contextlib import contextmanager
import os

_configured = False

def configure_telemetry(service_name="traceroot"):
    global _configured
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if _configured or not endpoint: return bool(endpoint)
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    provider = TracerProvider(resource=Resource.create({"service.name":service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/")+"/v1/traces")))
    trace.set_tracer_provider(provider); _configured = True
    return True

@contextmanager
def span(name, attributes=None):
    try:
        configure_telemetry()
        from opentelemetry import trace
        with trace.get_tracer("traceroot").start_as_current_span(name, attributes=attributes or {}) as current:
            yield current
    except ImportError:
        yield None

def add_event(name, attributes=None):
    try:
        from opentelemetry import trace
        current = trace.get_current_span()
        if current.is_recording(): current.add_event(name, attributes=attributes or {})
    except ImportError:
        pass
