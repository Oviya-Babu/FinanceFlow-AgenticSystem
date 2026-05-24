import logging
import os
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

    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)
    _provider = TracerProvider()

    otlp_endpoint = os.getenv("OTEL_EXPORTER_ENDPOINT", "")
    otlp_headers_raw = os.getenv("OTEL_EXPORTER_HEADERS", "")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            headers: dict = {}
            if otlp_headers_raw:
                import base64
                decoded = base64.b64decode(otlp_headers_raw + "==").decode("utf-8", errors="replace")
                for part in decoded.split(","):
                    if "=" in part:
                        k, _, v = part.partition("=")
                        headers[k.strip()] = v.strip()

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers)
            _provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTel OTLP exporter configured → %s", otlp_endpoint)
        except Exception as e:
            logger.warning("OTel OTLP exporter setup failed (%s) — falling back to console", e)
            _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel console exporter active (set OTEL_EXPORTER_ENDPOINT for remote export)")

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
