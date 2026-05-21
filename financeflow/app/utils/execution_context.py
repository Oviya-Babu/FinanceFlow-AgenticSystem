"""
Execution context tracking for correlation and tracing.
Provides request-scoped context for observability.
"""
from contextvars import ContextVar
from typing import Optional, Dict, Any
import uuid

# Context variables
_execution_context: ContextVar[Optional['ExecutionContext']] = ContextVar('execution_context', default=None)


class ExecutionContext:
    """Context for tracking execution across async operations."""

    def __init__(
        self,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_role: Optional[str] = None,
    ):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.trace_id = trace_id or str(uuid.uuid4())
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.metadata: Dict[str, Any] = {}
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value."""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value."""
        return self.metadata.get(key, default)


def get_execution_context() -> ExecutionContext:
    """Get current execution context or create new one."""
    ctx = _execution_context.get()
    if ctx is None:
        ctx = ExecutionContext()
        set_execution_context(ctx)
    return ctx


def set_execution_context(context: ExecutionContext) -> None:
    """Set execution context."""
    _execution_context.set(context)


def reset_execution_context() -> None:
    """Reset execution context (for testing)."""
    _execution_context.set(None)
