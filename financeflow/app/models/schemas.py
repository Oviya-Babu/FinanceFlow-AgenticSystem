"""
Data models for API requests and responses.
Pydantic models for type validation and serialization.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class ToolCall(BaseModel):
    """Model for a tool execution call."""
    tool_name: str = Field(..., description="Name of the tool to execute")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="Tool input parameters")
    tool_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique tool execution ID")


class ToolResult(BaseModel):
    """Model for tool execution result."""
    tool_name: str
    tool_id: str
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentMessage(BaseModel):
    """Message exchanged between agents."""
    sender_id: str = Field(..., description="Agent ID sending the message")
    receiver_id: str = Field(..., description="Agent ID receiving the message")
    message_type: str = Field(..., description="Type of message: task, result, query")
    content: Dict[str, Any] = Field(..., description="Message content")
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkflowRequest(BaseModel):
    """Request to start a workflow."""
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str = Field(..., description="Name of the workflow")
    description: str = Field(..., description="Task description")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=1, ge=1, le=10)


class WorkflowStatus(BaseModel):
    """Workflow execution status."""
    workflow_id: str
    status: str  # pending, running, completed, failed
    progress: int = Field(default=0, ge=0, le=100)
    current_agent: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class SessionContext(BaseModel):
    """Agent session context."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionMetadata(BaseModel):
    """Execution metadata for observability."""
    trace_id: str
    correlation_id: str
    session_id: str
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_name: Optional[str] = None
    execution_duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None
