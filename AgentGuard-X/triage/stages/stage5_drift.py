import asyncio
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import STAGE5_TIMEOUT
from triage.models import StageResult, TriageRequest
from session import redis_store

logger = logging.getLogger(__name__)

EXFIL_SEQUENCE = ("read_file", "http_post")
RECON_SEQUENCE_TOOL = "web_search"
RECON_SEQUENCE_COUNT = 3
LOOP_THRESHOLD = 5
LOOP_WINDOW = 10
TEMPORAL_THRESHOLD_SECONDS = 1.0
TEMPORAL_WINDOW = 5
SCOPE_CREEP_THRESHOLD = 3


def _compute_drift(session: list, baseline: list, request: TriageRequest) -> tuple[float, str, dict]:
    signals = []
    details = {}

    recent = session[-LOOP_WINDOW:] if len(session) >= LOOP_WINDOW else session
    recent_tools = [e["tool_name"] for e in recent]

    # Tool frequency drift
    if baseline:
        baseline_freq: dict[str, float] = {}
        for e in baseline:
            t = e.get("tool_name", "")
            baseline_freq[t] = baseline_freq.get(t, 0) + 1
        total_baseline = len(baseline) or 1
        for tool, cnt in baseline_freq.items():
            baseline_freq[tool] = cnt / total_baseline

        recent_freq: dict[str, float] = {}
        for t in recent_tools:
            recent_freq[t] = recent_freq.get(t, 0) + 1
        total_recent = len(recent_tools) or 1
        for tool in recent_freq:
            recent_freq[tool] = recent_freq[tool] / total_recent

        current_tool_baseline = baseline_freq.get(request.tool_name, 0.0)
        current_tool_recent = recent_freq.get(request.tool_name, 0.0)
        freq_drift = abs(current_tool_recent - current_tool_baseline)
        if freq_drift > 0.4:
            signals.append(0.5)
            details["freq_drift"] = round(freq_drift, 3)

    # Sequence anomaly: read_file → http_post within last 3 events
    last3_tools = [e["tool_name"] for e in session[-3:]] if len(session) >= 1 else []
    if (
        request.tool_name == EXFIL_SEQUENCE[1]
        and EXFIL_SEQUENCE[0] in last3_tools
    ):
        signals.append(0.75)
        details["sequence_anomaly"] = f"{EXFIL_SEQUENCE[0]}→{EXFIL_SEQUENCE[1]} exfiltration pattern detected"

    # Reconnaissance: web_search × 3 in recent
    if request.tool_name == RECON_SEQUENCE_TOOL:
        recon_count = sum(1 for t in recent_tools if t == RECON_SEQUENCE_TOOL)
        if recon_count >= RECON_SEQUENCE_COUNT - 1:
            signals.append(0.40)
            details["recon_pattern"] = f"web_search called {recon_count + 1} times in last {len(recent_tools)} requests"

    # Runaway loop: same tool ≥ 5× in last 10
    tool_count_recent = sum(1 for t in recent_tools if t == request.tool_name)
    if tool_count_recent >= LOOP_THRESHOLD:
        signals.append(0.70)
        details["loop_signal"] = f"Tool '{request.tool_name}' called {tool_count_recent + 1} times in {len(recent_tools)} requests"

    # Temporal anomaly: rapid requests
    if len(session) >= TEMPORAL_WINDOW:
        recent_timestamps = [e.get("timestamp", 0) for e in session[-TEMPORAL_WINDOW:]]
        recent_timestamps.append(request.timestamp)
        recent_timestamps.sort()
        intervals = [
            recent_timestamps[i + 1] - recent_timestamps[i]
            for i in range(len(recent_timestamps) - 1)
        ]
        fast_intervals = [iv for iv in intervals if iv < TEMPORAL_THRESHOLD_SECONDS]
        if len(fast_intervals) >= TEMPORAL_WINDOW - 1:
            signals.append(0.50)
            details["temporal_anomaly"] = f"Requests arriving at machine speed ({len(fast_intervals)} intervals < 1s)"

    # Scope escalation: read_file on 3+ distinct paths
    if request.tool_name == "read_file":
        paths_seen = set()
        for e in session:
            if e.get("tool_name") == "read_file":
                paths_seen.add(e.get("tool_input_raw", ""))
        current_path = request.tool_input_raw
        paths_seen.add(current_path)
        if len(paths_seen) >= SCOPE_CREEP_THRESHOLD:
            signals.append(0.45)
            details["scope_creep"] = f"read_file called on {len(paths_seen)} distinct paths"

    if not signals:
        drift_score = 0.0
        reason = "No behavioral drift detected. Session within normal parameters."
    else:
        drift_score = min(1.0, sum(signals) / len(signals) + 0.1 * (len(signals) - 1))
        reason = f"Behavioral drift detected: {'; '.join(details.values())}."

    return drift_score, reason, details


async def evaluate(request: TriageRequest) -> StageResult:
    try:
        loop = asyncio.get_running_loop()

        def _load_state():
            session = redis_store.get_session(request.session_id)
            baseline = redis_store.get_baseline(request.agent_role)
            return session, baseline

        session, baseline = await asyncio.wait_for(
            loop.run_in_executor(None, _load_state),
            timeout=STAGE5_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Stage 5 Redis timed out")
        return StageResult(
            stage=5,
            score=0.5,
            triggered=False,
            reason="Behavioral drift stage timed out — defaulting to elevated risk.",
            details={"error": "timeout"},
        )
    except Exception as e:
        logger.error("Stage 5 error loading state: %s", e)
        return StageResult(
            stage=5,
            score=0.5,
            triggered=False,
            reason="Behavioral drift stage unavailable — Redis error.",
            details={"error": str(e)},
        )

    drift_score, reason, details = _compute_drift(session, baseline, request)

    # Append current event to session (best-effort — don't fail the stage)
    try:
        new_event = {
            "tool_name": request.tool_name,
            "tool_input_raw": request.tool_input_raw,
            "timestamp": request.timestamp,
            "score": drift_score,
        }
        await asyncio.get_running_loop().run_in_executor(
            None, redis_store.append_to_session, request.session_id, new_event
        )
    except Exception as e:
        logger.warning("Stage 5 failed to append session event: %s", e)

    triggered = drift_score >= 0.3

    return StageResult(
        stage=5,
        score=drift_score,
        triggered=triggered,
        reason=reason,
        details={**details, "session_length": len(session), "baseline_length": len(baseline)},
    )
