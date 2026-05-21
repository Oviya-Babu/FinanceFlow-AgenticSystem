import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_provider: TracerProvider = None
_tracer = None


def init_otel(service_name: str = "agentguard-x") -> None:
    global _provider, _tracer
    if _provider is not None:
        return
    _provider = TracerProvider()
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer(service_name)
    logger.info("OpenTelemetry initialized for service: %s", service_name)


def get_tracer():
    if _tracer is None:
        init_otel()
    return _tracer


def record_triage_span(triage_response) -> None:
    tracer = get_tracer()
    if tracer is None:
        return
    try:
        with tracer.start_as_current_span("triage_decision") as span:
            span.set_attribute("agent_id", triage_response.agent_id)
            span.set_attribute("tool_name", triage_response.tool_name)
            span.set_attribute("routing_decision", triage_response.routing_decision)
            span.set_attribute("final_score", triage_response.final_score)
            span.set_attribute("processing_time_ms", triage_response.processing_time_ms)
            span.set_attribute("instant_kill", triage_response.instant_kill)
    except Exception as e:
        logger.warning("OTel span recording failed: %s", e)
