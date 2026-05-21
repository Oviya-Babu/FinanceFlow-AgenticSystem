"""
Workflow API routes for initiating and managing agent workflows.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, Optional
import asyncio

from app.config.logging import logger
from app.observability.telemetry import get_tracer
from app.models.schemas import WorkflowRequest, WorkflowStatus
from app.agents.orchestrator import OrchestratorAgent

tracer = get_tracer(__name__)

router = APIRouter()

# Global workflow tracking (in production, use Redis)
_active_workflows: Dict[str, Dict[str, Any]] = {}


@router.post("/workflows/start", response_model=Dict[str, Any], tags=["Workflows"])
async def start_workflow(request: WorkflowRequest, background_tasks: BackgroundTasks):
    """
    Start a new workflow.
    
    Args:
        request: Workflow request with description and parameters
        background_tasks: Background tasks for async execution
        
    Returns:
        Workflow status with ID
    """
    with tracer.start_as_current_span("start_workflow") as span:
        span.set_attribute("workflow_id", request.workflow_id)
        span.set_attribute("workflow_name", request.workflow_name)
        
        logger.info(
            f"Starting workflow: {request.workflow_name}",
            extra={
                "workflow_id": request.workflow_id,
                "description": request.description[:50]
            }
        )
        
        # Initialize workflow status
        workflow_status = {
            "workflow_id": request.workflow_id,
            "status": "pending",
            "progress": 0,
            "started_at": None,
            "completed_at": None,
            "error": None
        }
        
        _active_workflows[request.workflow_id] = workflow_status
        
        # Start orchestrator in background
        background_tasks.add_task(
            _execute_workflow,
            request
        )
        
        return {
            "workflow_id": request.workflow_id,
            "status": "pending",
            "message": f"Workflow {request.workflow_name} queued for execution"
        }


@router.get("/workflows/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """
    Get workflow status.
    
    Args:
        workflow_id: Workflow identifier
        
    Returns:
        Workflow status
    """
    with tracer.start_as_current_span("get_workflow_status") as span:
        span.set_attribute("workflow_id", workflow_id)
        
        if workflow_id not in _active_workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return _active_workflows[workflow_id]


@router.get("/workflows", response_model=Dict[str, Any])
async def list_workflows():
    """List all active workflows."""
    with tracer.start_as_current_span("list_workflows"):
        return {
            "count": len(_active_workflows),
            "workflows": list(_active_workflows.values())
        }


async def _execute_workflow(request: WorkflowRequest) -> None:
    """
    Execute a workflow (background task).
    
    Args:
        request: Workflow request
    """
    with tracer.start_as_current_span("execute_workflow") as span:
        span.set_attribute("workflow_id", request.workflow_id)
        
        try:
            # Update status to running
            _active_workflows[request.workflow_id]["status"] = "running"
            
            logger.info(
                f"Executing workflow: {request.workflow_name}",
                extra={"workflow_id": request.workflow_id}
            )
            
            # Create and run orchestrator
            orchestrator = OrchestratorAgent()
            await orchestrator.initialize_session()
            
            result = await orchestrator.execute_task(
                task_description=request.description,
                context=request.parameters
            )
            
            # Update status to completed
            _active_workflows[request.workflow_id]["status"] = "completed"
            _active_workflows[request.workflow_id]["result"] = result
            
            logger.info(
                f"Workflow completed: {request.workflow_name}",
                extra={"workflow_id": request.workflow_id}
            )
            
            span.set_attribute("status", "completed")
            
        except Exception as e:
            logger.error(
                f"Workflow failed: {e}",
                extra={
                    "workflow_id": request.workflow_id,
                    "error": str(e)
                }
            )
            
            _active_workflows[request.workflow_id]["status"] = "failed"
            _active_workflows[request.workflow_id]["error"] = str(e)
            span.set_attribute("status", "failed")
            span.set_attribute("error", str(e))


__all__ = ["router"]
