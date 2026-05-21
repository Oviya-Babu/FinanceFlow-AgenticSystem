import asyncio
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import RAG_SIMILARITY_THRESHOLD, RAG_TOP_K, STAGE4_TIMEOUT
from triage.models import StageResult, TriageRequest
from rag import knowledge_base

logger = logging.getLogger(__name__)


async def evaluate(request: TriageRequest) -> StageResult:
    try:
        loop = asyncio.get_running_loop()
        hits = await asyncio.wait_for(
            loop.run_in_executor(None, knowledge_base.query, request.tool_input_raw, RAG_TOP_K),
            timeout=STAGE4_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Stage 4 RAG query timed out")
        return StageResult(
            stage=4,
            score=0.5,
            triggered=False,
            reason="RAG stage timed out — semantic scoring suspended.",
            details={"error": "timeout"},
        )
    except Exception as e:
        logger.error("Stage 4 RAG error: %s", e)
        return StageResult(
            stage=4,
            score=0.5,
            triggered=False,
            reason="RAG stage unavailable — semantic scoring suspended.",
            details={"error": str(e)},
        )

    if not hits:
        return StageResult(
            stage=4,
            score=0.0,
            triggered=False,
            reason="No semantically similar threats found in knowledge base.",
            details={"hits": 0},
        )

    best = max(hits, key=lambda h: h["similarity"])
    similarity = best["similarity"]

    if similarity < RAG_SIMILARITY_THRESHOLD:
        return StageResult(
            stage=4,
            score=similarity,
            triggered=False,
            reason=f"Closest threat '{best['metadata']['title']}' similarity {similarity:.3f} below threshold {RAG_SIMILARITY_THRESHOLD}.",
            details={"best_match": best["metadata"]["title"], "similarity": similarity},
        )

    fpr = best["metadata"].get("false_positive_rate", 0.0)
    adjusted_score = similarity * (1.0 - fpr)
    owasp_ref = best["metadata"].get("owasp_ref", "")
    mitre_ref = best["metadata"].get("mitre_ref", "")

    return StageResult(
        stage=4,
        score=adjusted_score,
        triggered=True,
        reason=(
            f"Semantic match: '{best['metadata']['title']}' (similarity {similarity:.3f}, "
            f"FP-adjusted score {adjusted_score:.3f}). "
            f"OWASP {owasp_ref} / MITRE {mitre_ref}."
        ),
        details={
            "matched_threat": best["metadata"]["title"],
            "similarity": similarity,
            "adjusted_score": adjusted_score,
            "false_positive_rate": fpr,
            "owasp_ref": owasp_ref,
            "mitre_ref": mitre_ref,
            "recommended_action": best["metadata"].get("recommended_action", ""),
            "top_hits": [
                {"title": h["metadata"]["title"], "similarity": h["similarity"]}
                for h in hits[:3]
            ],
        },
    )
