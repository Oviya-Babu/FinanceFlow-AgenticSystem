from typing import List
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    WEIGHT_SIGNATURE, WEIGHT_POLICY, WEIGHT_SEMANTIC, WEIGHT_DRIFT,
    CORROBORATION_THRESHOLD, CORROBORATION_MULTIPLIER,
    FAST_PATH_THRESHOLD, INSTANT_KILL_THRESHOLD,
)
from triage.models import StageResult, TriageRequest, TriageResponse


def aggregate(
    request: TriageRequest,
    stage_results: List[StageResult],
    instant_kill: bool = False,
) -> TriageResponse:
    stage_map = {r.stage: r for r in stage_results}

    s2 = stage_map.get(2)
    s3 = stage_map.get(3)
    s4 = stage_map.get(4)
    s5 = stage_map.get(5)

    s2_score = s2.score if s2 else 0.0
    s3_score = s3.score if s3 else 0.0
    s4_score = s4.score if s4 else 0.0
    s5_score = s5.score if s5 else 0.0

    weighted = (
        s2_score * WEIGHT_SIGNATURE
        + s3_score * WEIGHT_POLICY
        + s4_score * WEIGHT_SEMANTIC
        + s5_score * WEIGHT_DRIFT
    )

    stages_above_half = sum(
        1 for score in (s2_score, s3_score, s4_score, s5_score) if score > 0.5
    )
    corroborated = False
    if stages_above_half >= CORROBORATION_THRESHOLD:
        weighted = min(1.0, weighted * CORROBORATION_MULTIPLIER)
        corroborated = True

    final_score = round(weighted, 4)

    if instant_kill:
        routing = "BLOCK"
    elif final_score >= INSTANT_KILL_THRESHOLD:
        routing = "BLOCK"
    elif final_score < FAST_PATH_THRESHOLD:
        routing = "FAST_PATH"
    else:
        routing = "SANDBOX"

    owasp_category = None
    if s4 and s4.triggered:
        owasp_category = s4.details.get("owasp_ref")

    explanation = _build_explanation(
        request, stage_map, final_score, routing, instant_kill, corroborated, owasp_category
    )

    return TriageResponse(
        request_id=request.request_id,
        agent_id=request.agent_id,
        tool_name=request.tool_name,
        final_score=final_score,
        routing_decision=routing,
        instant_kill=instant_kill,
        stage_results=stage_results,
        explanation=explanation,
        owasp_category=owasp_category,
    )


def _build_explanation(
    request: TriageRequest,
    stage_map: dict,
    final_score: float,
    routing: str,
    instant_kill: bool,
    corroborated: bool,
    owasp_category: str,
) -> str:
    parts = []

    s2 = stage_map.get(2)
    if s2 and s2.triggered:
        parts.append(s2.reason)

    s3 = stage_map.get(3)
    if s3 and s3.triggered:
        parts.append(s3.reason)

    s4 = stage_map.get(4)
    if s4 and s4.triggered:
        parts.append(s4.reason)

    s5 = stage_map.get(5)
    if s5 and s5.triggered:
        parts.append(s5.reason)

    if not parts:
        parts.append(f"All stages returned clean results for tool '{request.tool_name}'.")

    if corroborated:
        parts.append(f"Corroboration multiplier applied ({CORROBORATION_MULTIPLIER}x) — multiple independent signals agree.")

    score_text = f"Combined score {final_score:.2f}."
    parts.append(score_text)

    if instant_kill:
        parts.append(f"Decision: BLOCK (INSTANT KILL). Request blocked without aggregation.")
    else:
        decision_map = {
            "BLOCK": "Decision: BLOCK. Request rejected.",
            "SANDBOX": "Decision: SANDBOX. Executing in isolated Docker container for behavioral fingerprinting.",
            "FAST_PATH": "Decision: FAST PATH. Request approved — executing normally.",
        }
        parts.append(decision_map.get(routing, f"Decision: {routing}."))

    if owasp_category:
        parts.append(f"OWASP {owasp_category}.")

    return " ".join(parts)
