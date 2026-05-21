"""
OpenTelemetry observability setup with optional Jaeger exporter.
Provides distributed tracing for all platform operations.
"""
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

from prometheus_client import start_http_server

from app.config.settings import config
from app.config.logging import logger


_tracer_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None


def setup_observability() -> None:
    """
    Initialize OpenTelemetry tracing with Jaeger (if available).
    Sets up Jaeger exporter and auto-instrumentation for all subsystems.
    """
    global _tracer_provider, _tracer
    
    if not config.opentelemetry.enabled:
        logger.info("OpenTelemetry disabled in configuration")
        return
    
    logger.info("Initializing OpenTelemetry observability...")
    
    # Setup Jaeger exporter for distributed tracing (optional)
    _tracer_provider = None
    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        
        jaeger_exporter = JaegerExporter(
            agent_host_name=config.opentelemetry.jaeger_agent_host,
            agent_port=config.opentelemetry.jaeger_agent_port,
        )
        
        # Use TraceIdRatioBased sampler
        sampler = TraceIdRatioBased(config.opentelemetry.jaeger_sampler_param)
        
        _tracer_provider = TracerProvider(sampler=sampler)
        
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(jaeger_exporter)
        )
        
        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(__name__)
        
        logger.info(
            "Jaeger exporter configured",
            extra={
                "host": config.opentelemetry.jaeger_agent_host,
                "port": config.opentelemetry.jaeger_agent_port
            }
        )
    except (ImportError, Exception) as e:
        logger.info(f"Jaeger exporter not available: {e}")
        _tracer_provider = TracerProvider()
        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(__name__)
    
    # Setup Prometheus metrics exporter (if enabled)
    try:
        if config.prometheus.enabled:
            # Start Prometheus HTTP server
            start_http_server(port=config.prometheus.port, addr=config.prometheus.host)
            logger.info(
                "Prometheus metrics server started",
                extra={"port": config.prometheus.port, "host": config.prometheus.host}
            )
    except Exception as e:
        logger.warning(f"Failed to setup Prometheus metrics: {e}")
    
    # Auto-instrument FastAPI (optional)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument()
        logger.info("FastAPI instrumented")
    except Exception as e:
        logger.debug(f"FastAPI instrumentation not available: {e}")
    
    # Auto-instrument SQLAlchemy (optional)
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy instrumented")
    except Exception as e:
        logger.debug(f"SQLAlchemy instrumentation not available: {e}")
    
    # Auto-instrument Redis (optional)
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.info("Redis instrumented")
    except Exception as e:
        logger.debug(f"Redis instrumentation not available: {e}")
    
    # Auto-instrument HTTP libraries (optional)
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        RequestsInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTP libraries instrumented")
    except Exception as e:
        logger.debug(f"HTTP instrumentation not available: {e}")


def get_tracer(name: str) -> trace.Tracer:
    """
    Get tracer instance for creating spans.
    
    Args:
        name: Module or component name
        
    Returns:
        Tracer instance
    """
    if _tracer_provider is None:
        setup_observability()
    
    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    else:
        # Return no-op tracer if disabled
        return trace.get_tracer(name)


def get_meter(name: str):
    """
    Get meter instance for recording metrics.
    Simplified version focusing on Prometheus client library.
    
    Args:
        name: Module or component name
        
    Returns:
        Meter name string
    """
    return name


# Convenience exports
__all__ = [
    "setup_observability",
    "get_tracer",
    "get_meter",
]
