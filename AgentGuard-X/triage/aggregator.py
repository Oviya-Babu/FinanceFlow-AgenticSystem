from typing import List
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CORROBORATION_THRESHOLD, CORROBORATION_MULTIPLIER,
    FAST_PATH_THRESHOLD, INSTANT_KILL_THRESHOLD,
)
from triage.models import StageResult, TriageRequest, TriageResponse

# Weights per spec: Stage2=35%, Stage4=30%, Stage5=20%, Stage7=15%
# Stage3 (OPA) is categorical (block/allow), not weighted in aggregate.
# Stage6 (rate limit) is categorical (block if triggered).
_WEIGHTS = {2: 0.35, 4: 0.30, 5: 0.20, 7: 0.15}


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
    s7 = stage_map.get(7)

    s2_score = s2.score if s2 else 0.0
    s4_score = s4.score if s4 else 0.0
    s5_score = s5.score if s5 else 0.0
    s7_score = s7.score if s7 else 0.0

    weighted = (
        s2_score * _WEIGHTS[2]
        + s4_score * _WEIGHTS[4]
        + s5_score * _WEIGHTS[5]
        + s7_score * _WEIGHTS[7]
    )

    stages_above_half = sum(
        1 for score in (s2_score, s4_score, s5_score, s7_score) if score > 0.5
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
    mitre_ref = None
    if s4 and s4.triggered:
        owasp_category = s4.details.get("owasp_ref")
        mitre_ref = s4.details.get("mitre_ref")

    explanation = _build_explanation(
        request, stage_map, final_score, routing, instant_kill, corroborated,
        owasp_category, s2_score, s4_score, s5_score, s7_score,
    )

    # Stage 8 — Final Aggregation result (transparent scoring)
    s8 = StageResult(
        stage=8,
        score=final_score,
        triggered=routing in ("BLOCK", "SANDBOX"),
        reason=_s8_reason(routing, final_score, s2_score, s4_score, s5_score, s7_score, corroborated),
        details={
            "stage2_weighted": round(s2_score * _WEIGHTS[2], 4),
            "stage4_weighted": round(s4_score * _WEIGHTS[4], 4),
            "stage5_weighted": round(s5_score * _WEIGHTS[5], 4),
            "stage7_weighted": round(s7_score * _WEIGHTS[7], 4),
            "stage2_weight": _WEIGHTS[2],
            "stage4_weight": _WEIGHTS[4],
            "stage5_weight": _WEIGHTS[5],
            "stage7_weight": _WEIGHTS[7],
            "final_score": final_score,
            "corroborated": corroborated,
            "routing_decision": routing,
            "threshold_allow": FAST_PATH_THRESHOLD,
            "threshold_block": INSTANT_KILL_THRESHOLD,
        },
    )

    all_stages = [r for r in stage_results] + [s8]
    all_stages.sort(key=lambda r: r.stage)

    return TriageResponse(
        request_id=request.request_id,
        agent_id=request.agent_id,
        tool_name=request.tool_name,
        final_score=final_score,
        routing_decision=routing,
        instant_kill=instant_kill,
        corroboration_applied=corroborated,
        stage_results=all_stages,
        explanation=explanation,
        owasp_category=owasp_category,
        mitre_ref=mitre_ref,
    )


def _s8_reason(routing, final_score, s2, s4, s5, s7, corroborated) -> str:
    formula = (
        f"({s2:.4f}×0.35) + ({s4:.4f}×0.30) + ({s5:.4f}×0.20) + ({s7:.4f}×0.15)"
        f" = {final_score:.4f}"
    )
    threshold_note = {
        "FAST_PATH": f"≤{FAST_PATH_THRESHOLD} → ALLOW",
        "SANDBOX":   f">{FAST_PATH_THRESHOLD} and <{INSTANT_KILL_THRESHOLD} → SANDBOX",
        "BLOCK":     f"≥{INSTANT_KILL_THRESHOLD} → BLOCK",
    }.get(routing, routing)
    corr = " [corroboration ×1.25 applied]" if corroborated else ""
    return f"Weighted aggregate: {formula}{corr}. {threshold_note}"


def _build_explanation(
    request, stage_map, final_score, routing, instant_kill, corroborated,
    owasp_category, s2_score, s4_score, s5_score, s7_score,
) -> str:
    parts = []

    for stage_num in (2, 3, 4, 5, 6, 7):
        sr = stage_map.get(stage_num)
        if sr and sr.triggered:
            parts.append(sr.reason)

    if not parts:
        parts.append(f"All stages returned clean results for tool '{request.tool_name}'.")

    if corroborated:
        parts.append(f"Corroboration multiplier applied ({CORROBORATION_MULTIPLIER}×) — multiple independent signals agree.")

    parts.append(f"Combined score {final_score:.4f}.")

    if instant_kill:
        parts.append("Decision: BLOCK (INSTANT KILL). Request blocked without full aggregation.")
    else:
        decision_map = {
            "BLOCK":     "Decision: BLOCK. Request rejected.",
            "SANDBOX":   "Decision: SANDBOX. Executing in isolated container for behavioral analysis.",
            "FAST_PATH": "Decision: FAST PATH. Request approved — executing normally.",
        }
        parts.append(decision_map.get(routing, f"Decision: {routing}."))

    if owasp_category:
        parts.append(f"OWASP {owasp_category}.")

    return " ".join(parts)
