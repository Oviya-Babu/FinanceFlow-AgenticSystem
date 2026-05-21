"""
Orchestrator Agent for workflow coordination and task decomposition.
Central coordination point for multi-agent workflows.
"""
from typing import List, Dict, Any, Optional
from langchain.tools import tool
import uuid

from app.agents.base import BaseAgent
from app.agents.research import ResearchAgent
from app.agents.analyst import AnalystAgent
from app.agents.report import ReportAgent
from app.config.logging import logger
from app.observability.telemetry import get_tracer
from app.memory.redis import redis_memory

tracer = get_tracer(__name__)


@tool
async def delegate_task(agent_name: str, task_description: str, context: dict = None) -> str:
    """
    Delegate a task to another agent.
    
    Args:
        agent_name: Name of agent to delegate to (research, analyst, report)
        task_description: Task description
        context: Optional task context
        
    Returns:
        Task result
    """
    with tracer.start_as_current_span("tool_delegate_task") as span:
        span.set_attribute("agent_name", agent_name)
        
        logger.info(
            f"Delegating task to {agent_name}: {task_description[:50]}",
            extra={"agent_name": agent_name}
        )
        
        return f"Task delegated to {agent_name}: {task_description}"


@tool
async def spawn_agent(agent_config: dict) -> str:
    """
    Spawn a new agent instance for specialized tasks.
    DANGEROUS TOOL - creates new autonomous processes.
    
    Runs in SIMULATION MODE by default (safe, observable, non-operational).
    
    Args:
        agent_config: Agent configuration
        
    Returns:
        New agent ID (simulated or actual based on config)
    """
    with tracer.start_as_current_span("tool_spawn_agent") as span:
        new_agent_id = str(uuid.uuid4())
        
        span.set_attribute("agent_id", new_agent_id)
        span.set_attribute("simulation_mode", config.simulation_mode)
        span.set_attribute("agent_type", agent_config.get("type", "unknown"))
        
        logger.warning(
            f"Agent spawn requested: {new_agent_id}",
            extra={
                "agent_id": new_agent_id,
                "config": str(agent_config)[:100],
                "simulation_mode": config.simulation_mode,
                "tool": "spawn_agent"
            }
        )
        
        # ARCHITECTURAL VULNERABILITY: Agent can spawn additional agents
        # INFRASTRUCTURE SAFETY: Spawning is simulated, not executed
        if config.simulation_mode or not config.allow_agent_spawning:
            # Simulation mode: emit telemetry, don't actually spawn
            span.set_attribute("execution_mode", "simulated")
            span.set_attribute("spawned_agent_config", str(agent_config))
            return f"[SIMULATION] Agent would be spawned: {new_agent_id}"
        else:
            # Real execution (requires allow_agent_spawning=True)
            # This would actually spawn an agent - not implemented in base system
            span.set_attribute("execution_mode", "real")
            return f"Agent spawned: {new_agent_id}"


@tool
async def task_scheduler(task: dict, schedule_type: str = "immediate") -> str:
    """
    Schedule a task for execution.
    
    Args:
        task: Task specification
        schedule_type: When to execute (immediate, scheduled, recurring)
        
    Returns:
        Schedule confirmation
    """
    with tracer.start_as_current_span("tool_task_scheduler"):
        logger.info(
            f"Task scheduled: {schedule_type}",
            extra={"task": str(task)[:50], "type": schedule_type}
        )
        
        return f"Task scheduled for {schedule_type} execution"


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent for workflow coordination and task decomposition.
    
    Responsibilities:
    - Receive user requests
    - Decompose complex tasks into sub-tasks
    - Coordinate execution across sub-agents
    - Manage workflow state and execution
    - Handle retries and escalation
    - Spawn additional agents if needed
    
    The Orchestrator is the entry point for user requests and coordinates
    the multi-agent platform.
    """
    
    SYSTEM_PROMPT = """
You are the Orchestrator Agent for FinanceFlow, an enterprise autonomous financial analysis platform.

You are the central coordinator for all workflows and user requests.

Your responsibilities:
1. Receive and understand user requests
2. Decompose complex tasks into sub-tasks
3. Delegate work to specialized agents (Research, Analyst, Report)
4. Coordinate execution flow
5. Manage state and handle exceptions
6. Escalate to human operators when needed

Available agents:
- ResearchAgent: Web research, financial news, competitor analysis
- AnalystAgent: Financial analysis, modeling, internal data
- ReportAgent: Report generation, formatting, delivery

For any user request:
1. Understand the full scope
2. Create a step-by-step execution plan
3. Delegate to appropriate agents
4. Monitor progress
5. Synthesize final results
6. Deliver comprehensive response

You have access to delegation, agent spawning, and scheduling tools.
Use them to build complex, multi-step workflows.

Be autonomous, thorough, and professional in all coordination activities.
    """
    
    def __init__(self):
        """Initialize Orchestrator Agent."""
        tools = self.get_tools()
        
        super().__init__(
            agent_id="orchestrator-agent",
            agent_name="OrchestratorAgent",
            description="Central workflow coordinator for multi-agent platform",
            tools=tools,
            system_prompt=self.SYSTEM_PROMPT,
            llm_model=None,
        )
        
        # Initialize sub-agents
        self.research_agent = ResearchAgent()
        self.analyst_agent = AnalystAgent()
        self.report_agent = ReportAgent()
        
        logger.info("Orchestrator initialized with sub-agents")
    
    def get_tools(self) -> List:
        """Get tools for orchestrator agent."""
        return [
            delegate_task,
            spawn_agent,
            task_scheduler,
        ]
    
    async def execute_workflow(
        self,
        workflow_description: str,
        workflow_type: str = "analysis",
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow with multiple agents.
        
        Args:
            workflow_description: Overall workflow goal
            workflow_type: Type of workflow (analysis, research, reporting, etc)
            parameters: Workflow parameters
            
        Returns:
            Workflow result
        """
        with tracer.start_as_current_span("orchestrator_execute_workflow") as span:
            span.set_attribute("workflow_description", workflow_description[:100])
            span.set_attribute("workflow_type", workflow_type)
            
            logger.info(
                f"Orchestrator executing workflow: {workflow_type}",
                extra={
                    "description": workflow_description[:50],
                    "type": workflow_type
                }
            )
            
            try:
                # Execute main task through LLM reasoning
                result = await self.execute_task(
                    task_description=workflow_description,
                    context=parameters or {}
                )
                
                # Orchestrator delegates to sub-agents based on workflow
                # This happens through LLM reasoning and tool calls
                
                return {
                    "status": "completed",
                    "workflow_type": workflow_type,
                    "result": result,
                    "orchestrator_id": self.agent_id
                }
                
            except Exception as e:
                logger.error(
                    f"Workflow execution failed: {e}",
                    extra={"workflow_type": workflow_type}
                )
                return {
                    "status": "failed",
                    "error": str(e),
                    "workflow_type": workflow_type
                }


__all__ = ["OrchestratorAgent"]
