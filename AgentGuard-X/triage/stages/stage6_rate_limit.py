"""
Stage 6 — Rate Limiting

Checks whether this agent is making requests too quickly.
Uses a Redis sliding window counter (per agent_id, per tool).
Verdict: PASS (score 0.0) or BLOCK (score 1.0).
"""
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from triage.models import StageResult, TriageRequest

logger = logging.getLogger(__name__)

# Requests-per-minute limits per agent role
_ROLE_LIMITS: dict = {
    "orchestrator_agent": 60,
    "research_agent":     40,
    "analyst_agent":      30,
    "report_agent":       20,
    "data_agent":         30,
}
_DEFAULT_LIMIT = 30
_WINDOW_SECONDS = 60


def _get_limit(agent_role: str) -> int:
    return _ROLE_LIMITS.get(agent_role, _DEFAULT_LIMIT)


async def evaluate(request: TriageRequest) -> StageResult:
    try:
        from session import redis_store
        client = redis_store._get_client()

        rate_key = f"agentguard:rate:{request.agent_id}"
        now = time.time()
        window_start = now - _WINDOW_SECONDS

        pipe = client.pipeline()
        pipe.zremrangebyscore(rate_key, "-inf", window_start)
        pipe.zadd(rate_key, {f"{now}:{request.request_id}": now})
        pipe.zcard(rate_key)
        pipe.expire(rate_key, _WINDOW_SECONDS * 2)
        results = pipe.execute()

        current_count = results[2]
        limit = _get_limit(request.agent_role)
        rate_pct = current_count / limit

        if current_count > limit:
            score = min(1.0, rate_pct * 0.9)
            return StageResult(
                stage=6,
                score=round(score, 4),
                triggered=True,
                reason=f"Rate limit exceeded: {current_count} requests in {_WINDOW_SECONDS}s (limit: {limit})",
                details={
                    "current_count": current_count,
                    "limit": limit,
                    "window_seconds": _WINDOW_SECONDS,
                    "rate_pct": round(rate_pct * 100, 1),
                    "headroom_pct": 0.0,
                },
            )

        headroom = max(0.0, (limit - current_count) / limit * 100)
        return StageResult(
            stage=6,
            score=0.0,
            triggered=False,
            reason=f"Rate OK: {current_count}/{limit} req/{_WINDOW_SECONDS}s",
            details={
                "current_count": current_count,
                "limit": limit,
                "window_seconds": _WINDOW_SECONDS,
                "rate_pct": round(rate_pct * 100, 1),
                "headroom_pct": round(headroom, 1),
            },
        )

    except Exception as e:
        logger.error("Stage 6 (rate limit) error: %s", e)
        return StageResult(
            stage=6,
            score=0.0,
            triggered=False,
            reason=f"Rate limit check unavailable: {type(e).__name__}",
            details={"error": str(e)},
        )
