import asyncio
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx

from config import OPA_URL, OPA_POLICY_PATH, STAGE3_TIMEOUT
from triage.models import StageResult, TriageRequest
from session import redis_store

logger = logging.getLogger(__name__)

VIOLATION_SCORES = {
    "tool_not_permitted":    0.90,
    "rate_limit_exceeded":   0.60,
    "resource_scope_violation": 0.75,
}


async def evaluate(request: TriageRequest) -> StageResult:
    request_count = redis_store.get_request_count_last_minute(request.agent_id)

    payload = {
        "input": {
            "agent_role": request.agent_role,
            "tool_name":  request.tool_name,
            "tool_input": request.tool_input,
            "request_count_last_minute": request_count,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=STAGE3_TIMEOUT) as client:
            resp = await client.post(OPA_URL + OPA_POLICY_PATH, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("OPA unreachable or error: %s", e)
        return StageResult(
            stage=3,
            score=0.5,
            triggered=False,
            reason="OPA unavailable — policy stage defaulting to elevated risk.",
            details={"error": str(e)},
        )

    result = data.get("result", {})
    allowed = result.get("allow", False)
    reason_text = result.get("reason", "unknown")
    violation_type = result.get("violation_type", "unknown")

    if allowed:
        return StageResult(
            stage=3,
            score=0.0,
            triggered=False,
            reason=f"Policy evaluation: tool '{request.tool_name}' is permitted for role '{request.agent_role}'.",
            details={"allow": True, "request_count": request_count},
        )

    score = VIOLATION_SCORES.get(violation_type, 0.75)
    return StageResult(
        stage=3,
        score=score,
        triggered=True,
        reason=f"Policy violation: {reason_text}. Tool '{request.tool_name}' blocked for role '{request.agent_role}'.",
        details={
            "allow": False,
            "violation_type": violation_type,
            "policy_reason": reason_text,
            "request_count": request_count,
        },
    )
