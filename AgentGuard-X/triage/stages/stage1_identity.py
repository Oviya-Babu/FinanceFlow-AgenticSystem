import logging
import re

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import REGISTERED_AGENTS
from triage.models import StageResult, TriageRequest
from session import redis_store

logger = logging.getLogger(__name__)

# Role inference from agent_id prefix (mirrors /execute endpoint logic)
_ROLE_PREFIXES = [
    ("research",    "research_agent"),
    ("analyst",     "analyst_agent"),
    ("report",      "report_agent"),
    ("orchestrat",  "orchestrator_agent"),
    ("data",        "data_agent"),
    ("admin",       "admin_agent"),
]


def _infer_role(agent_id: str) -> str | None:
    low = agent_id.lower()
    for prefix, role in _ROLE_PREFIXES:
        if prefix in low:
            return role
    return None


async def evaluate(request: TriageRequest) -> StageResult:
    # Primary: check exact registry match
    agent_info = REGISTERED_AGENTS.get(request.agent_id)
    registered_role = agent_info["role"] if agent_info else None

    # Secondary: infer role from name pattern (supports dynamic/test agent IDs)
    if registered_role is None:
        registered_role = _infer_role(request.agent_id)

    if registered_role is None:
        return StageResult(
            stage=1,
            score=1.0,
            triggered=True,
            reason=f"Unregistered agent identity '{request.agent_id}'. Cannot infer role.",
            details={"agent_id": request.agent_id},
        )

    if request.agent_role != registered_role:
        return StageResult(
            stage=1,
            score=1.0,
            triggered=True,
            reason=(
                f"Role spoofing detected. Agent '{request.agent_id}' claimed role "
                f"'{request.agent_role}' but expected '{registered_role}'."
            ),
            details={"claimed_role": request.agent_role, "registered_role": registered_role},
        )

    if not request.session_id or not request.session_id.strip():
        return StageResult(
            stage=1,
            score=1.0,
            triggered=True,
            reason="session_id must not be empty.",
            details={"session_id": request.session_id},
        )

    redis_store.init_session(request.session_id)

    return StageResult(
        stage=1,
        score=0.0,
        triggered=False,
        reason="Agent identity verified. Session active.",
        details={"agent_id": request.agent_id, "role": registered_role, "session_id": request.session_id},
    )
