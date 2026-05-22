"""
Base tool definitions for FinanceFlow agents.
Tools are the executable capabilities agents can use.
"""
from typing import Any, Dict, Optional, List
from abc import ABC, abstractmethod
from datetime import datetime

from langchain_core.tools import BaseTool
from app.config.logging import logger
from app.observability.telemetry import get_tracer

tracer = get_tracer(__name__)


class FinanceFlowTool(BaseTool, ABC):
    """
    Base class for FinanceFlow tools.
    All tools must implement this interface.
    """
    
    def __init__(self, name: str, description: str):
        """Initialize tool."""
        super().__init__(name=name, description=description)
        self.execution_count = 0
        self.last_execution = None
    
    @abstractmethod
    async def _async_execute(self, **kwargs) -> Any:
        """
        Async execute the tool.
        Subclasses must implement this.
        """
        pass
    
    def _run(self, **kwargs) -> Any:
        """
        Synchronous run (called by LangChain).
        Delegates to async implementation.
        """
        import asyncio
        
        with tracer.start_as_current_span("tool_execution") as span:
            span.set_attribute("tool_name", self.name)
            span.set_attribute("tool_input", str(kwargs)[:100])
            
            self.execution_count += 1
            self.last_execution = datetime.utcnow()
            
            try:
                # Get or create event loop for async execution
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(self._async_execute(**kwargs))
                
                logger.info(
                    f"Tool executed: {self.name}",
                    extra={
                        "tool_name": self.name,
                        "execution_count": self.execution_count
                    }
                )
                
                span.set_attribute("status", "success")
                return result
                
            except Exception as e:
                logger.error(
                    f"Tool execution failed: {self.name}: {e}",
                    extra={"tool_name": self.name, "error": str(e)}
                )
                span.set_attribute("status", "error")
                span.set_attribute("error", str(e))
                raise
    
    async def arun(self, **kwargs) -> Any:
        """Async run implementation."""
        return await self._async_execute(**kwargs)


# Marker for dangerous tools (will be used by AgentGuard-X)
class DangerousTool(FinanceFlowTool):
    """Marker class for tools that require runtime security validation."""
    is_dangerous = True


__all__ = ["FinanceFlowTool", "DangerousTool"]
