import json
import logging
from typing import List, Optional

import redis

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    REDIS_HOST, REDIS_PORT,
    SESSION_KEY_PREFIX, BASELINE_KEY_PREFIX,
    SESSION_WINDOW_SIZE,
)

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _client


def get_session(session_id: str) -> List[dict]:
    try:
        raw = _get_client().get(SESSION_KEY_PREFIX + session_id)
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.error("Redis get_session failed: %s", e)
        return []


def append_to_session(session_id: str, event: dict) -> None:
    try:
        client = _get_client()
        key = SESSION_KEY_PREFIX + session_id
        raw = client.get(key)
        events: List[dict] = json.loads(raw) if raw else []
        events.append(event)
        if len(events) > SESSION_WINDOW_SIZE:
            events = events[-SESSION_WINDOW_SIZE:]
        client.set(key, json.dumps(events))
    except Exception as e:
        logger.error("Redis append_to_session failed: %s", e)


def init_session(session_id: str) -> None:
    try:
        client = _get_client()
        key = SESSION_KEY_PREFIX + session_id
        if not client.exists(key):
            client.set(key, json.dumps([]))
    except Exception as e:
        logger.error("Redis init_session failed: %s", e)


def get_baseline(agent_role: str) -> List[dict]:
    try:
        raw = _get_client().get(BASELINE_KEY_PREFIX + agent_role)
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.error("Redis get_baseline failed: %s", e)
        return []


def set_baseline(agent_role: str, events: List[dict]) -> None:
    try:
        _get_client().set(BASELINE_KEY_PREFIX + agent_role, json.dumps(events))
    except Exception as e:
        logger.error("Redis set_baseline failed: %s", e)


def get_request_count_last_minute(agent_id: str) -> int:
    try:
        key = f"agentguard:ratelimit:{agent_id}"
        val = _get_client().get(key)
        return int(val) if val else 0
    except Exception as e:
        logger.error("Redis get_request_count failed: %s", e)
        return 0


def increment_request_count(agent_id: str) -> None:
    try:
        client = _get_client()
        key = f"agentguard:ratelimit:{agent_id}"
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        pipe.execute()
    except Exception as e:
        logger.error("Redis increment_request_count failed: %s", e)


def is_healthy() -> bool:
    try:
        _get_client().ping()
        return True
    except Exception:
        return False
