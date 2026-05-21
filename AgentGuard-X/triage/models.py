from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel


class TriageRequest(BaseModel):
    agent_id: str
    session_id: str
    tool_name: str
    tool_input: dict
    tool_input_raw: str
    agent_role: str
    timestamp: float
    request_id: str


class StageResult(BaseModel):
    stage: int
    score: float
    triggered: bool
    reason: str
    details: Dict = {}


class TriageResponse(BaseModel):
    request_id: str
    agent_id: str
    tool_name: str
    final_score: float
    routing_decision: str  # FAST_PATH | SANDBOX | BLOCK
    instant_kill: bool
    stage_results: List[StageResult]
    explanation: str
    owasp_category: Optional[str] = None
    processing_time_ms: float = 0.0


class SandboxVerdict(BaseModel):
    verdict: str  # PROMOTE | KILL
    fingerprint: dict
    reason: str
    execution_ms: float


class SanitizerResult(BaseModel):
    pii_detected: bool
    pii_entities: List[dict]
    injection_detected: bool
    injection_patterns: List[str]
    risk_level: str
    recommendation: str
