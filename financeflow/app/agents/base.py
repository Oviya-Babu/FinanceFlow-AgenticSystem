"""
Base agent framework with dynamic tool execution and async coordination.
Implements autonomous agent with reasoning, memory, and inter-agent communication.
"""
import asyncio
from typing import Any, Dict, List, Optional, Callable
from abc import ABC, abstractmethod
import uuid
from datetime import datetime

try:
    from langchain.agents import create_react_agent, AgentExecutor
except ImportError:
    from langchain.agents.react.agent import create_react_agent
    from langchain.agents.agent import AgentExecutor
from langchain_core.tools import BaseTool, tool
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

from app.config.logging import logger, LogContext
from app.config.settings import config
from app.observability.telemetry import get_tracer
from app.memory.redis import redis_memory
from app.models.schemas import AgentMessage, ToolResult, SessionContext
from app.utils.execution_context import ExecutionContext, get_execution_context
from app.security.guard_bridge import AgentGuardCallback, ToolBlockedException, AGENTGUARD_ENABLED


tracer = get_tracer(__name__)


class BaseAgent(ABC):
    """
    Base autonomous agent with dynamic reasoning, tool execution, and memory.
    
    Agents operate independently, reason about tasks, and can communicate
    with other agents asynchronously.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_role: str,
        agent_name: str,
        description: str,
        tools: List[BaseTool],
        system_prompt: str,
        llm_model: Optional[str] = None,
        max_iterations: Optional[int] = None,
        timeout: Optional[int] = None
    ):
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.agent_name = agent_name
        self.description = description
        self.tools = tools
        self.system_prompt = system_prompt
        self.llm_model = llm_model or config.ollama.model
        self.max_iterations = max_iterations or config.agent_max_iterations
        self.timeout = timeout or config.agent_timeout
        
        # LLM instance — OllamaLLM is the langchain-ollama 0.2.x replacement
        # for the deprecated langchain_community.llms.Ollama
        self.llm = OllamaLLM(
            model=self.llm_model,
            base_url=config.ollama.host,
            temperature=config.ollama.temperature,
            top_p=config.ollama.top_p,
        )
        
        # Session and execution tracking
        self.current_session: Optional[SessionContext] = None
        self.execution_history: List[Dict[str, Any]] = []
        self.tool_execution_log: List[ToolResult] = []
        
        logger.info(
            f"Agent initialized: {agent_name}",
            extra={
                "agent_id": agent_id,
                "tool_count": len(tools),
                "model": self.llm_model
            }
        )
    
    async def initialize_session(self) -> SessionContext:
        """Initialize session, reusing the workflow-level session_id when present."""
        with tracer.start_as_current_span("agent_initialize_session") as span:
            span.set_attribute("agent_id", self.agent_id)

            # Reuse the workflow session_id so all agents in one workflow
            # share a single session — required for AgentGuard-X drift detection.
            ctx = get_execution_context()
            self.current_session = SessionContext(
                session_id=ctx.session_id,
                agent_id=self.agent_id,
                correlation_id=ctx.correlation_id or LogContext.get_correlation_id(),
                trace_id=ctx.trace_id or LogContext.get_trace_id(),
            )
            
            # Store session in Redis
            await redis_memory.set_session(
                self.current_session.session_id,
                self.current_session.model_dump()
            )
            
            logger.info(
                "Session initialized",
                extra={
                    "session_id": self.current_session.session_id,
                    "agent_id": self.agent_id
                }
            )
            
            return self.current_session
    
    async def execute_task(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a task autonomously with dynamic reasoning.
        
        Args:
            task_description: Description of task to execute
            context: Additional context for the task
            
        Returns:
            Task result dictionary
        """
        with tracer.start_as_current_span("agent_execute_task") as span:
            span.set_attribute("agent_id", self.agent_id)
            span.set_attribute("task_description", task_description[:100])
            
            if self.current_session is None:
                await self.initialize_session()
            
            logger.info(
                f"Agent executing task: {task_description[:50]}...",
                extra={
                    "agent_id": self.agent_id,
                    "session_id": self.current_session.session_id,
                    "task_length": len(task_description)
                }
            )
            
            try:
                # Create agent executor
                agent_executor = self._create_agent_executor()
                
                # Prepare input with context
                agent_input = {
                    "input": task_description,
                    "context": context or {},
                }
                
                # Execute with timeout
                start_time = datetime.utcnow()
                result = await asyncio.wait_for(
                    asyncio.to_thread(agent_executor.invoke, agent_input),
                    timeout=self.timeout
                )
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Store execution history
                execution_record = {
                    "timestamp": datetime.utcnow(),
                    "task": task_description,
                    "result": result,
                    "duration_ms": duration_ms,
                    "status": "completed"
                }
                self.execution_history.append(execution_record)
                
                # Store in Redis for persistence
                await redis_memory.append_memory(
                    f"agent:{self.agent_id}:history",
                    f"Task: {task_description}\nResult: {result}\nDuration: {duration_ms}ms"
                )
                
                span.set_attribute("duration_ms", duration_ms)
                span.set_attribute("status", "completed")
                
                logger.info(
                    "Task completed successfully",
                    extra={
                        "agent_id": self.agent_id,
                        "duration_ms": duration_ms,
                        "task": task_description[:50]
                    }
                )
                
                return {
                    "status": "completed",
                    "result": result.get("output", result),
                    "duration_ms": duration_ms,
                    "agent_id": self.agent_id
                }
                
            except ToolBlockedException as e:
                logger.warning(
                    "Tool blocked by AgentGuard-X: %s",
                    e,
                    extra={"agent_id": self.agent_id, "task": task_description[:50]},
                )
                span.set_attribute("status", "blocked")
                span.set_attribute("block_reason", str(e))
                return {
                    "status": "blocked",
                    "error": str(e),
                    "agent_id": self.agent_id,
                }

            except asyncio.TimeoutError:
                logger.error(
                    "Task execution timeout",
                    extra={
                        "agent_id": self.agent_id,
                        "timeout": self.timeout
                    }
                )
                span.set_attribute("status", "timeout")
                return {
                    "status": "timeout",
                    "error": f"Execution exceeded {self.timeout}s timeout",
                    "agent_id": self.agent_id
                }
            
            except Exception as e:
                logger.error(
                    f"Task execution failed: {e}",
                    extra={
                        "agent_id": self.agent_id,
                        "error": str(e)
                    }
                )
                span.set_attribute("status", "failed")
                return {
                    "status": "failed",
                    "error": str(e),
                    "agent_id": self.agent_id
                }
    
    def _create_agent_executor(self) -> AgentExecutor:
        """Create LangChain agent executor with tools and AgentGuard-X callback."""
        tools_description = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in self.tools]
        )

        prompt = PromptTemplate.from_template(
            self.system_prompt + "\n\n"
            "Available tools:\n" + tools_description
        )

        agent = create_react_agent(self.llm, self.tools, prompt)

        callbacks = []
        if AGENTGUARD_ENABLED and self.current_session is not None:
            callbacks.append(AgentGuardCallback(
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                session_id=self.current_session.session_id,
            ))

        executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=self.tools,
            verbose=config.fastapi.debug,
            max_iterations=self.max_iterations,
            handle_parsing_errors=True,
            callbacks=callbacks or None,
        )

        return executor
    
    async def send_message(
        self,
        receiver_id: str,
        message_type: str,
        content: Dict[str, Any]
    ) -> AgentMessage:
        """
        Send message to another agent.
        
        Args:
            receiver_id: ID of receiving agent
            message_type: Type of message
            content: Message content
            
        Returns:
            Sent message with ID
        """
        with tracer.start_as_current_span("agent_send_message") as span:
            span.set_attribute("sender_id", self.agent_id)
            span.set_attribute("receiver_id", receiver_id)
            span.set_attribute("message_type", message_type)
            
            message = AgentMessage(
                sender_id=self.agent_id,
                receiver_id=receiver_id,
                message_type=message_type,
                content=content
            )
            
            # Store message in Redis for inter-agent communication
            await redis_memory.set_session(
                f"message:{message.message_id}",
                message.model_dump(),
                ttl=300  # 5 minute TTL for messages
            )
            
            logger.info(
                f"Message sent from {self.agent_id} to {receiver_id}",
                extra={
                    "message_id": message.message_id,
                    "message_type": message_type
                }
            )
            
            return message
    
    async def get_memory(self) -> str:
        """Get agent memory from Redis."""
        return await redis_memory.get_memory(f"agent:{self.agent_id}:history")
    
    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """
        Get tools for this agent.
        Subclasses must implement this.
        """
        pass
    
    async def shutdown(self) -> None:
        """Clean shutdown of agent."""
        logger.info(
            f"Agent shutting down: {self.agent_name}",
            extra={"agent_id": self.agent_id}
        )
        self.execution_history.clear()


__all__ = ["BaseAgent"]
