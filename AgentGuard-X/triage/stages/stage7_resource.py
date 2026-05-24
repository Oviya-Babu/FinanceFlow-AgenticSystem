"""
Stage 7 — Resource Consumption

Tracks per-agent API call budget, compute credits, and cumulative
tool usage. Blocks agents that exhaust their allocated budget.
"""
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from triage.models import StageResult, TriageRequest

logger = logging.getLogger(__name__)

# Per-agent daily budgets
_ROLE_BUDGETS: dict = {
    "orchestrator_agent": {"api_calls": 2000, "compute_credits": 5000},
    "research_agent":     {"api_calls": 1000, "compute_credits": 2000},
    "analyst_agent":      {"api_calls": 800,  "compute_credits": 3000},
    "report_agent":       {"api_calls": 500,  "compute_credits": 1000},
    "data_agent":         {"api_calls": 600,  "compute_credits": 1500},
}
_DEFAULT_BUDGET = {"api_calls": 500, "compute_credits": 1000}
_BUDGET_WINDOW  = 86400  # 24 hours


def _get_budget(agent_role: str) -> dict:
    return _ROLE_BUDGETS.get(agent_role, _DEFAULT_BUDGET)


async def evaluate(request: TriageRequest) -> StageResult:
    try:
        from session import redis_store
        client = redis_store._get_client()

        budget = _get_budget(request.agent_role)
        api_limit    = budget["api_calls"]
        credit_limit = budget["compute_credits"]

        api_key    = f"agentguard:budget:api:{request.agent_id}"
        credit_key = f"agentguard:budget:credits:{request.agent_id}"

        pipe = client.pipeline()
        pipe.incr(api_key)
        pipe.expire(api_key, _BUDGET_WINDOW)
        pipe.incr(credit_key)
        pipe.expire(credit_key, _BUDGET_WINDOW)
        results = pipe.execute()

        api_used    = results[0]
        credit_used = results[2]

        api_pct    = api_used / api_limit * 100
        credit_pct = credit_used / credit_limit * 100
        max_pct    = max(api_pct, credit_pct)

        details = {
            "api_calls_used":     api_used,
            "api_calls_limit":    api_limit,
            "api_calls_pct":      round(api_pct, 1),
            "compute_credits_used":  credit_used,
            "compute_credits_limit": credit_limit,
            "compute_credits_pct":   round(credit_pct, 1),
            "budget_window_hours": _BUDGET_WINDOW // 3600,
            "budget_remaining_pct": round(100 - max_pct, 1),
        }

        if api_used > api_limit or credit_used > credit_limit:
            score = min(1.0, max_pct / 100 * 0.95)
            return StageResult(
                stage=7,
                score=round(score, 4),
                triggered=True,
                reason=(
                    f"Resource budget exceeded: "
                    f"API {api_used}/{api_limit} ({api_pct:.1f}%), "
                    f"credits {credit_used}/{credit_limit} ({credit_pct:.1f}%)"
                ),
                details=details,
            )

        if max_pct > 85:
            score = (max_pct - 85) / 15 * 0.3
            return StageResult(
                stage=7,
                score=round(score, 4),
                triggered=True,
                reason=f"Resource usage high: {max_pct:.1f}% of budget consumed",
                details=details,
            )

        return StageResult(
            stage=7,
            score=0.0,
            triggered=False,
            reason=f"Resources OK: API {api_pct:.1f}%, credits {credit_pct:.1f}% used",
            details=details,
        )

    except Exception as e:
        logger.error("Stage 7 (resource) error: %s", e)
        return StageResult(
            stage=7,
            score=0.0,
            triggered=False,
            reason=f"Resource check unavailable: {type(e).__name__}",
            details={"error": str(e)},
        )
