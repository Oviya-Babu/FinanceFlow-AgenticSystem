import json
import logging
from typing import List, Optional

import redis

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
    SESSION_KEY_PREFIX, BASELINE_KEY_PREFIX,
    SESSION_WINDOW_SIZE,
)

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None

EVENTS_KEY = "agentguard:events"
EVENTS_MAX  = 1000

# Atomic append-and-trim via Lua so concurrent calls cannot race on read-modify-write.
_APPEND_SCRIPT = """
local key      = KEYS[1]
local event    = ARGV[1]
local max_size = tonumber(ARGV[2])
local raw = redis.call('GET', key)
local events
if raw then
    events = cjson.decode(raw)
else
    events = {}
end
table.insert(events, cjson.decode(event))
if #events > max_size then
    local trimmed = {}
    for i = #events - max_size + 1, #events do
        table.insert(trimmed, events[i])
    end
    events = trimmed
end
redis.call('SET', key, cjson.encode(events))
return #events
"""


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        kwargs = dict(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=False,
        )
        if REDIS_PASSWORD:
            kwargs["password"] = REDIS_PASSWORD
        _client = redis.Redis(**kwargs)
    return _client


def is_healthy() -> bool:
    try:
        _get_client().ping()
        return True
    except Exception:
        return False


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
        client.eval(_APPEND_SCRIPT, 1, key, json.dumps(event), SESSION_WINDOW_SIZE)
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


def push_event_to_stream(event: dict) -> None:
    """Push a security event to the global events list (newest first, capped at 1000)."""
    try:
        client = _get_client()
        pipe = client.pipeline()
        pipe.lpush(EVENTS_KEY, json.dumps(event))
        pipe.ltrim(EVENTS_KEY, 0, EVENTS_MAX - 1)
        pipe.execute()
    except Exception as e:
        logger.error("Redis push_event_to_stream failed: %s", e)


def store_agent_session(agent_id: str, role: str, tool_name: str, verdict: str) -> None:
    """Create or update a user-facing session under session:{agent_id}."""
    from datetime import datetime
    try:
        client = _get_client()
        key = f"session:{agent_id}"
        now = datetime.utcnow().isoformat()
        raw = client.get(key)
        if raw:
            session = json.loads(raw)
        else:
            session = {
                "agent_id": agent_id,
                "role": role,
                "created_at": now,
                "tools_called": [],
                "request_count": 0,
                "decisions": [],
            }
        session["last_request"] = now
        session["tools_called"].append(tool_name)
        session["request_count"] += 1
        session["decisions"].append(verdict)
        client.setex(key, 86400, json.dumps(session))
    except Exception as e:
        logger.error("Redis store_agent_session failed: %s", e)


def increment_verdict_counter(verdict: str) -> None:
    """Increment the simple verdict counter verdict:{verdict} for metrics/auditing."""
    try:
        _get_client().incr(f"verdict:{verdict}")
    except Exception as e:
        logger.error("Redis increment_verdict_counter failed: %s", e)


def log_decision(agent_id: str, verdict: str, risk_score: float, trace_id: str, tool_name: str) -> None:
    """Append a decision record to decisions:{agent_id} list (capped at 100)."""
    from datetime import datetime
    import time as _time
    try:
        client = _get_client()
        key = f"decisions:{agent_id}"
        record = json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": verdict,
            "risk_score": risk_score,
            "trace_id": trace_id,
            "tool_name": tool_name,
        })
        pipe = client.pipeline()
        pipe.lpush(key, record)
        pipe.ltrim(key, 0, 99)
        pipe.execute()
        # Timeline sorted set
        ts = _time.time()
        client.zadd("decisions_timeline", {f"{agent_id}:{verdict}:{ts}": ts})
    except Exception as e:
        logger.error("Redis log_decision failed: %s", e)


def get_recent_events(limit: int = 50, since_timestamp: Optional[float] = None) -> List[dict]:
    """Retrieve recent events from the stream, newest first."""
    try:
        client = _get_client()
        raw_items = client.lrange(EVENTS_KEY, 0, max(limit * 2, 200) - 1)
        events = []
        for raw in raw_items:
            try:
                evt = json.loads(raw)
                if since_timestamp is not None:
                    ts = evt.get("timestamp", 0)
                    if ts <= since_timestamp:
                        continue
                events.append(evt)
                if len(events) >= limit:
                    break
            except Exception:
                pass
        return events
    except Exception as e:
        logger.error("Redis get_recent_events failed: %s", e)
        return []
