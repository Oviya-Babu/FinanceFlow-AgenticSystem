"""
Structured logging setup with JSON formatting and correlation IDs.
"""
import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from app.config.settings import config


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_dict: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
            "module": record.module,
        }
        
        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_dict["correlation_id"] = record.correlation_id
        
        # Add trace ID if present
        if hasattr(record, "trace_id"):
            log_dict["trace_id"] = record.trace_id
        
        # Add extra fields
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_dict.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_dict["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_dict)


class PlainFormatter(logging.Formatter):
    """Simple plain text formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        base = f"[{record.levelname}] {record.name} - {record.getMessage()}"
        if record.exc_info:
            base += "\n" + "".join(traceback.format_exception(*record.exc_info))
        return base


def setup_logging(name: str = "financeflow") -> logging.Logger:
    """
    Configure and return a logger with JSON formatting.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set log level
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Add formatter based on config
    if config.logging.format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = PlainFormatter()
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


class LogContext:
    """Context manager for correlation IDs and trace context."""
    
    _correlation_id: Optional[str] = None
    _trace_id: Optional[str] = None
    
    @classmethod
    def set_correlation_id(cls, correlation_id: str) -> None:
        """Set current correlation ID."""
        cls._correlation_id = correlation_id
    
    @classmethod
    def get_correlation_id(cls) -> str:
        """Get or generate correlation ID."""
        if cls._correlation_id is None:
            cls._correlation_id = str(uuid.uuid4())
        return cls._correlation_id
    
    @classmethod
    def set_trace_id(cls, trace_id: str) -> None:
        """Set current trace ID."""
        cls._trace_id = trace_id
    
    @classmethod
    def get_trace_id(cls) -> str:
        """Get or generate trace ID."""
        if cls._trace_id is None:
            cls._trace_id = str(uuid.uuid4())
        return cls._trace_id
    
    @classmethod
    def reset(cls) -> None:
        """Reset context (useful for testing)."""
        cls._correlation_id = None
        cls._trace_id = None


# Root logger
logger = setup_logging()
