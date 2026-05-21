import asyncio
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.models import StageResult, TriageRequest, TriageResponse
from triage.stages import stage1_identity, stage2_signatures, stage3_policy, stage4_rag, stage5_drift
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
        resp = TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=1.0,
            routing_decision="BLOCK",
            instant_kill=False,
            stage_results=[s1],
            explanation=s1.reason,
            owasp_category=None,
            processing_time_ms=round(elapsed, 2),
        )
        return resp

    # Stages 2–5 run concurrently; return_exceptions prevents one stage crash
    # from aborting the whole gather and returning a 500 to the caller.
    raw = await asyncio.gather(
        stage2_signatures.evaluate(request),
        stage3_policy.evaluate(request),
        stage4_rag.evaluate(request),
        stage5_drift.evaluate(request),
        return_exceptions=True,
    )

    def _safe(result, stage_num: int) -> StageResult:
        if isinstance(result, StageResult):
            return result
        logger.error("Stage %d raised unhandled exception: %s", stage_num, result)
        return _skipped(stage_num, f"Stage {stage_num} internal error: {type(result).__name__}: {result}")

    s2, s3, s4, s5 = (_safe(raw[0], 2), _safe(raw[1], 3), _safe(raw[2], 4), _safe(raw[3], 5))

    # Check instant-kill from Stage 2 before aggregation
    instant_kill = s2.details.get("instant_kill", False)
    if instant_kill:
        elapsed = (time.time() - start) * 1000
        skip_reason = "Short-circuited by Stage 2 instant-kill."
        s3_result = _skipped(3, skip_reason)
        s4_result = _skipped(4, skip_reason)
        s5_result = _skipped(5, skip_reason)

        owasp_category = None
        explanation = (
            f"{s2.reason} "
            f"Instant kill threshold exceeded. Stages 3–5 cancelled. Request blocked."
        )
        resp = TriageResponse(
            request_id=request.request_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            final_score=s2.score,
            routing_decision="BLOCK",
            instant_kill=True,
            stage_results=[s1, s2, s3_result, s4_result, s5_result],
            explanation=explanation,
            owasp_category="LLM06",
            processing_time_ms=round(elapsed, 2),
        )
        return resp

    # Increment request count for rate limiting
    try:
        redis_store.increment_request_count(request.agent_id)
    except Exception:
        pass

    result = aggregator.aggregate(request, [s1, s2, s3, s4, s5], instant_kill=False)
    result.processing_time_ms = round((time.time() - start) * 1000, 2)
    return result
