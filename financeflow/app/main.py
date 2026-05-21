"""
FastAPI application with async routes and middleware.
Main entry point for FinanceFlow platform.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import uuid

from app.config.settings import config
from app.config.logging import logger, LogContext
from app.observability.telemetry import setup_observability, get_tracer
from app.memory.redis import redis_memory
from app.services.database import db_manager, populate_sample_data
from app.api.routes import workflow_routes

tracer = get_tracer(__name__)


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("FinanceFlow platform starting up...")
    
    try:
        # Initialize Redis
        await redis_memory.connect()
        logger.info("Redis memory layer initialized")
        
        # Initialize database
        await db_manager.init_db()
        await populate_sample_data()
        logger.info("SQLite database initialized")
        
        # Initialize observability
        setup_observability()
        logger.info("Observability pipeline initialized")
        
        logger.info("FinanceFlow platform ready for requests")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("FinanceFlow platform shutting down...")
    
    try:
        # Disconnect Redis
        await redis_memory.disconnect()
        logger.info("Redis disconnected")
        
        # Close database
        await db_manager.close()
        logger.info("Database closed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    
    logger.info("FinanceFlow platform shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=config.name,
    description=config.description,
    version=config.version,
    lifespan=lifespan
)


# Middleware for request tracking and correlation IDs
@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    """
    Middleware to add correlation ID to all requests.
    Used for distributed tracing.
    """
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    
    # Set in context
    LogContext.set_correlation_id(correlation_id)
    LogContext.set_trace_id(trace_id)
    
    # Record request start
    start_time = time.time()
    
    # Add to response headers
    with tracer.start_as_current_span("http_request") as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        span.set_attribute("http.client_ip", request.client.host if request.client else "unknown")
        span.set_attribute("correlation_id", correlation_id)
        span.set_attribute("trace_id", trace_id)
        
        logger.info(
            f"HTTP {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
                "trace_id": trace_id
            }
        )
        
        try:
            response = await call_next(request)
            
            # Add correlation IDs to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Trace-ID"] = trace_id
            
            # Log response
            duration_ms = int((time.time() - start_time) * 1000)
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("duration_ms", duration_ms)
            
            logger.info(
                f"HTTP {response.status_code} {request.url.path}",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "path": request.url.path
                }
            )
            
            return response
            
        except Exception as e:
            logger.error(
                f"Request failed: {e}",
                extra={
                    "path": request.url.path,
                    "error": str(e),
                    "correlation_id": correlation_id
                }
            )
            span.set_attribute("error", str(e))
            raise


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    correlation_id = LogContext.get_correlation_id()
    
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "path": request.url.path,
            "error": str(exc),
            "correlation_id": correlation_id
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "correlation_id": correlation_id,
            "error": str(exc) if config.fastapi.debug else "Internal error"
        }
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for platform readiness."""
    with tracer.start_as_current_span("health_check"):
        return {
            "status": "healthy",
            "service": config.name,
            "version": config.version,
        }


# Include workflow routes
app.include_router(workflow_routes.router, prefix="/api", tags=["Workflows"])


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": config.name,
        "description": config.description,
        "version": config.version,
        "endpoints": {
            "health": "/health",
            "workflows": "/api/workflows",
            "metrics": "/metrics" if config.prometheus.enabled else None,
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.fastapi.host,
        port=config.fastapi.port,
        reload=config.fastapi.reload,
        log_level=config.logging.level.lower(),
    )
