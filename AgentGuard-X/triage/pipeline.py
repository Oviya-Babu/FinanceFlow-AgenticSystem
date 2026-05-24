import asyncio
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.models import StageResult, TriageRequest, TriageResponse
from triage.stages import (
    stage1_identity, stage2_signatures, stage3_policy,
    stage4_rag, stage5_drift,
)
from triage.stages import stage6_rate_limit, stage7_resource
from triage import aggregator
from session import redis_store

logger = logging.getLogger(__name__)


def _skipped(stage_num: int, reason: str) -> StageResult:
    return StageResult(
        stage=stage_num,
        score=0.0,
        triggered=False,
        reason=reason,
        details={"skipped": True},
    )


async def run_pipeline(request: TriageRequest) -> TriageResponse:
    start = time.time()

    # Stage 1 — hard gate, must pass before anything else
    s1 = await stage1_identity.evaluate(request)
    if s1.triggered:
        elapsed = (time.time() - start) * 1000
        skip = "Short-circuited by Stage 1 identity failure."
        s8 = StageResult(
            stage=8,
            score=1.0,
            triggered=True,
            reason="Identity validation failed — request blocked without further evaluation",
            details={"routing_decision": "BLOCK", "final_score": 1.0},
        )
        return TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=1.0,
            routing_decision="BLOCK",
            instant_kill=False,
            stage_results=[s1,
                _skipped(2, skip), _skipped(3, skip), _skipped(4, skip),
                _skipped(5, skip), _skipped(6, skip), _skipped(7, skip),
                s8,
            ],
            explanation=s1.reason,
            owasp_category=None,
            processing_time_ms=round(elapsed, 2),
        )

    # Stages 2–7 run concurrently where possible.
    # Stage 6 (rate limit) and 7 (resource) can run alongside 2-5.
    raw = await asyncio.gather(
        stage2_signatures.evaluate(request),
        stage3_policy.evaluate(request),
        stage4_rag.evaluate(request),
        stage5_drift.evaluate(request),
        stage6_rate_limit.evaluate(request),
        stage7_resource.evaluate(request),
        return_exceptions=True,
    )

    def _safe(result, stage_num: int) -> StageResult:
        if isinstance(result, StageResult):
            return result
        logger.error("Stage %d raised unhandled exception: %s", stage_num, result)
        return _skipped(stage_num, f"Stage {stage_num} error: {type(result).__name__}")

    s2 = _safe(raw[0], 2)
    s3 = _safe(raw[1], 3)
    s4 = _safe(raw[2], 4)
    s5 = _safe(raw[3], 5)
    s6 = _safe(raw[4], 6)
    s7 = _safe(raw[5], 7)

    # Stage 6 categorical block: rate limit exceeded always blocks
    if s6.triggered and s6.score >= 0.8:
        elapsed = (time.time() - start) * 1000
        skip = "Short-circuited by Stage 6 rate limit."
        s8 = StageResult(
            stage=8,
            score=1.0,
            triggered=True,
            reason="Rate limit exceeded — request blocked",
            details={"routing_decision": "BLOCK", "final_score": 1.0, "triggered_by": "stage6"},
        )
        return TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=1.0,
            routing_decision="BLOCK",
            instant_kill=False,
            stage_results=[s1, s2, s3, s4, s5, s6, s7, s8],
            explanation=s6.reason,
            owasp_category="LLM04",
            processing_time_ms=round(elapsed, 2),
        )

    # Stage 7 categorical block: resource budget exhausted
    if s7.triggered and s7.score >= 0.9:
        elapsed = (time.time() - start) * 1000
        s8 = StageResult(
            stage=8,
            score=1.0,
            triggered=True,
            reason="Resource budget exhausted — request blocked",
            details={"routing_decision": "BLOCK", "final_score": 1.0, "triggered_by": "stage7"},
        )
        return TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=1.0,
            routing_decision="BLOCK",
            instant_kill=False,
            stage_results=[s1, s2, s3, s4, s5, s6, s7, s8],
            explanation=s7.reason,
            owasp_category="LLM04",
            processing_time_ms=round(elapsed, 2),
        )

    # Instant-kill from Stage 2
    instant_kill = s2.details.get("instant_kill", False)
    if instant_kill:
        elapsed = (time.time() - start) * 1000
        skip = "Short-circuited by Stage 2 instant-kill."
        s8 = StageResult(
            stage=8,
            score=s2.score,
            triggered=True,
            reason="Instant-kill pattern detected — request blocked immediately",
            details={"routing_decision": "BLOCK", "final_score": s2.score, "triggered_by": "stage2_instant_kill"},
        )
        return TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=s2.score,
            routing_decision="BLOCK",
            instant_kill=True,
            stage_results=[
                s1, s2,
                _skipped(3, skip), _skipped(4, skip), _skipped(5, skip),
                s6, s7, s8,
            ],
            explanation=f"{s2.reason} Instant kill threshold exceeded. Stages 3–5 cancelled.",
            owasp_category="LLM06",
            processing_time_ms=round(elapsed, 2),
        )

    # Stage 8 — final aggregation
    result = aggregator.aggregate(request, [s1, s2, s3, s4, s5, s6, s7], instant_kill=False)
    result.processing_time_ms = round((time.time() - start) * 1000, 2)
    return result
