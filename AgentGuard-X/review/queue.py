import json
import logging
import time
from typing import Optional
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import REVIEW_QUEUE_KEY, REVIEW_QUEUE_SCORE_FLOOR
from triage.models import TriageResponse
from session.redis_store import _get_client

logger = logging.getLogger(__name__)


def enqueue(triage_response: TriageResponse, priority: Optional[float] = None) -> bool:
    if triage_response.final_score < REVIEW_QUEUE_SCORE_FLOOR and not triage_response.instant_kill:
        return False
    try:
        score = priority if priority is not None else triage_response.final_score
        payload = {
            "request_id": triage_response.request_id,
            "agent_id": triage_response.agent_id,
            "tool_name": triage_response.tool_name,
            "final_score": triage_response.final_score,
            "routing_decision": triage_response.routing_decision,
            "instant_kill": triage_response.instant_kill,
            "explanation": triage_response.explanation,
            "owasp_category": triage_response.owasp_category,
            "enqueued_at": time.time(),
        }
        _get_client().zadd(REVIEW_QUEUE_KEY, {json.dumps(payload): score})
        logger.info("Enqueued request %s for review (priority %.2f)", triage_response.request_id, score)
        return True
    except Exception as e:
        logger.error("Review queue enqueue failed: %s", e)
        return False


def dequeue() -> Optional[dict]:
    try:
        items = _get_client().zpopmax(REVIEW_QUEUE_KEY, 1)
        if not items:
            return None
        raw, score = items[0]
        payload = json.loads(raw)
        payload["priority_score"] = score
        return payload
    except Exception as e:
        logger.error("Review queue dequeue failed: %s", e)
        return None


def list_queue(limit: int = 20) -> list:
    try:
        items = _get_client().zrevrangebyscore(
            REVIEW_QUEUE_KEY, "+inf", "-inf", start=0, num=limit, withscores=True
        )
        result = []
        for raw, score in items:
            payload = json.loads(raw)
            payload["priority_score"] = score
            result.append(payload)
        return result
    except Exception as e:
        logger.error("Review queue list failed: %s", e)
        return []


def submit_decision(request_id: str, decision: str, analyst_notes: str) -> dict:
    audit = {
        "request_id": request_id,
        "decision": decision,
        "analyst_notes": analyst_notes,
        "timestamp": time.time(),
        "analyst_id": "demo_analyst",
    }
    try:
        audit_key = f"agentguard:audit:{request_id}"
        _get_client().set(audit_key, json.dumps(audit), ex=86400 * 30)

        # Auto-add to knowledge base
        if analyst_notes:
            try:
                from rag import knowledge_base
                new_entry = {
                    "id": f"analyst_{request_id[:8]}",
                    "title": f"Analyst Decision: {decision} for {request_id[:8]}",
                    "description": analyst_notes,
                    "severity": "high" if decision == "BLOCK" else "medium",
                    "owasp_ref": "",
                    "mitre_ref": "",
                    "false_positive_rate": 0.05 if decision == "BLOCK" else 0.20,
                    "recommended_action": decision.lower(),
                    "analyst_notes": analyst_notes,
                }
                knowledge_base.add_entry(new_entry)
                audit["rag_updated"] = True
            except Exception as e:
                logger.warning("Failed to add analyst decision to RAG: %s", e)
                audit["rag_updated"] = False

        logger.info("Analyst decision recorded: %s → %s", request_id, decision)
    except Exception as e:
        logger.error("Failed to record analyst decision: %s", e)
        audit["error"] = str(e)

    return audit


# FastAPI router
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/review", tags=["review"])


class DecisionRequest(BaseModel):
    request_id: str
    decision: str
    analyst_notes: str


@router.get("/queue")
def get_queue():
    return {"items": list_queue(), "count": len(list_queue())}


@router.post("/decision")
def post_decision(body: DecisionRequest):
    result = submit_decision(body.request_id, body.decision, body.analyst_notes)
    return result
