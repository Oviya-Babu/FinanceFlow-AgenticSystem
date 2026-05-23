from __future__ import annotations
import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

_AGENT_ID_RE  = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}$")
_TOOL_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
_ROLE_RE      = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class TriageRequest(BaseModel):
    agent_id:        str   = Field(..., min_length=2,  max_length=64)
    session_id:      str   = Field(..., min_length=1,  max_length=128)
    tool_name:       str   = Field(..., min_length=1,  max_length=64)
    tool_input:      dict
    tool_input_raw:  str   = Field(..., max_length=32_768)
    agent_role:      str   = Field(..., min_length=1,  max_length=32)
    timestamp:       float
    request_id:      str   = Field(..., min_length=1,  max_length=64)
    sequence_context: List[str] = Field(default_factory=list)
    financeflow_agent: str = Field(default="")

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError("agent_id must be lowercase alphanumeric with hyphens")
        return v

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, v: str) -> str:
        if not _TOOL_NAME_RE.match(v):
            raise ValueError("tool_name must be lowercase identifier with underscores")
        return v

    @field_validator("agent_role")
    @classmethod
    def _validate_agent_role(cls, v: str) -> str:
        if not _ROLE_RE.match(v):
            raise ValueError("agent_role must be lowercase alphanumeric with underscores")
        return v

    @field_validator("tool_input_raw")
    @classmethod
    def _no_null_bytes(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes not permitted in tool_input_raw")
        return v


class StageResult(BaseModel):
    stage:     int
    score:     float
    triggered: bool
    reason:    str
    details:   Dict = {}


class TriageResponse(BaseModel):
    request_id:           str
    agent_id:             str
    tool_name:            str
    final_score:          float
    routing_decision:     str        # FAST_PATH | SANDBOX | BLOCK
    instant_kill:         bool
    corroboration_applied: bool = False
    stage_results:        List[StageResult]
    explanation:          str
    owasp_category:       Optional[str] = None
    mitre_ref:            Optional[str] = None
    processing_time_ms:   float = 0.0


class SecurityEvent(BaseModel):
    """Broadcast over WebSocket and stored in Redis event stream."""
    request_id:           str
    agent_id:             str
    tool_name:            str
    final_score:          float
    routing_decision:     str
    instant_kill:         bool
    corroboration_applied: bool = False
    stage_results:        List[StageResult]
    explanation:          str
    owasp_category:       Optional[str] = None
    mitre_ref:            Optional[str] = None
    processing_time_ms:   float = 0.0
    event_type:           str = "triage_decision"
    financeflow_agent:    str = ""
    timestamp:            float = 0.0


class SandboxVerdict(BaseModel):
    verdict:      str    # PROMOTE | KILL
    fingerprint:  dict
    reason:       str
    execution_ms: float


class SanitizerResult(BaseModel):
    pii_detected:       bool
    pii_entities:       List[dict]
    injection_detected: bool
    injection_patterns: List[str]
    risk_level:         str
    recommendation:     str
    sanitized_output:   str = ""
