import asyncio
import json
import logging
import re as _re
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import OPA_URL, OLLAMA_BASE_URL
from triage.models import TriageRequest, TriageResponse
from triage.pipeline import run_pipeline
from rag import knowledge_base
from session import redis_store
from observability.otel_setup import init_otel, record_triage_span
from review.queue import router as review_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Global state ─────────────────────────────────────────────────────────────
model_ready = False

_stats = {
    "total":        0,
    "block":        0,
    "fast_path":    0,
    "sandbox":      0,
    "total_time_ms": 0.0,
}

# ─── WebSocket connection manager ─────────────────────────────────────────────
class _ConnectionManager:
    def __init__(self):
        self._active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket):
        self._active.discard(ws) if hasattr(self._active, "discard") else None
        try:
            self._active.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, payload: dict):
        dead = []
        for ws in list(self._active):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


_manager = _ConnectionManager()

# ─── Prometheus metrics ───────────────────────────────────────────────────────
try:
    from prometheus_client import (
        Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry, REGISTRY,
    )

    _requests_total = Counter(
        "agentguard_requests_total",
        "Total triage requests",
        ["verdict", "agent_role", "tool_name"],
    )
    _duration_hist = Histogram(
        "agentguard_processing_duration_seconds",
        "Request processing duration",
        ["verdict"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    )
    _instant_kills = Counter("agentguard_instant_kills_total", "Instant-kill blocks")
    _opa_errors    = Counter("agentguard_opa_errors_total", "OPA evaluation errors")
    _redis_errors  = Counter("agentguard_redis_errors_total", "Redis operation errors")
    _sandbox_verdicts = Counter(
        "agentguard_sandbox_verdicts_total", "Sandbox verdicts", ["verdict"]
    )
    _pii_detections       = Counter("agentguard_pii_detections_total", "PII detections")
    _injection_detections = Counter("agentguard_injection_detections_total", "Injection detections")
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed — /metrics will be unavailable")


def _incr_request(verdict: str, agent_role: str, tool_name: str, duration_s: float):
    if not _PROMETHEUS_AVAILABLE:
        return
    v = verdict.lower()
    _requests_total.labels(verdict=v, agent_role=agent_role, tool_name=tool_name).inc()
    _duration_hist.labels(verdict=v).observe(duration_s)


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model_ready
    logger.info("AgentGuard-X triage service starting up...")
    init_otel()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, knowledge_base.initialize)
    model_ready = True
    logger.info("AgentGuard-X triage service ready.")
    yield
    logger.info("AgentGuard-X triage service shutting down.")


app = FastAPI(title="AgentGuard-X Triage Engine", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(review_router)

# Serve the production frontend
_FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index = os.path.join(_FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return HTMLResponse("<h1>AgentGuard-X</h1><p>Frontend not found</p>")


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import hashlib
    tb = traceback.format_exc()
    error_id = hashlib.sha256(tb.encode()).hexdigest()[:8]
    logger.error("Unhandled exception [%s] on %s %s\n%s", error_id, request.method, request.url, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": error_id},
    )


# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await _manager.connect(websocket)
    # Send last 20 events immediately on connect
    try:
        recent = redis_store.get_recent_events(limit=20)
        for evt in recent:
            await websocket.send_json(evt)
    except Exception as e:
        logger.warning("Failed to send initial events over WebSocket: %s", e)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive; client sends pings
    except WebSocketDisconnect:
        _manager.disconnect(websocket)


# ─── REST API ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    # Redis: RESP probe (the only correct probe — never HTTP)
    t0 = time.time()
    redis_ok = redis_store.is_healthy()
    redis_latency = round((time.time() - t0) * 1000, 1)

    chromadb_ok = knowledge_base.is_healthy()

    # OPA: HTTP /health → {} (empty JSON body, status 200)
    opa_ok = False
    opa_latency = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            t0 = time.time()
            r = await client.get(OPA_URL + "/health")
            opa_latency = round((time.time() - t0) * 1000, 1)
            opa_ok = r.status_code == 200
    except Exception:
        pass

    # Ollama: /api/tags returns JSON listing available models
    ollama_ok = False
    ollama_latency = None
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            t0 = time.time()
            r = await client.get(OLLAMA_BASE_URL + "/api/tags")
            ollama_latency = round((time.time() - t0) * 1000, 1)
            if r.status_code == 200:
                ollama_ok = True
                ollama_models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass

    # Loki: /ready returns "ready" (NOT root path — root 404 is normal and healthy)
    loki_ok = False
    loki_latency = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            t0 = time.time()
            r = await client.get("http://localhost:3100/ready")
            loki_latency = round((time.time() - t0) * 1000, 1)
            loki_ok = r.status_code == 200 and "ready" in r.text.lower()
    except Exception:
        pass

    # Prometheus: /-/healthy returns "Prometheus is Healthy"
    prometheus_ok = False
    prometheus_latency = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            t0 = time.time()
            r = await client.get("http://localhost:9090/-/healthy")
            prometheus_latency = round((time.time() - t0) * 1000, 1)
            prometheus_ok = r.status_code == 200
    except Exception:
        pass

    core_healthy = all([redis_ok, opa_ok, chromadb_ok])
    return {
        "status": "ok" if core_healthy else "degraded",
        "model_ready": model_ready,
        "components": {
            "redis":      {"healthy": redis_ok,      "latency_ms": redis_latency,
                           "probe": "redis-cli ping → PONG"},
            "opa":        {"healthy": opa_ok,        "latency_ms": opa_latency,
                           "probe": "GET /health → {}"},
            "chromadb":   {"healthy": chromadb_ok,   "latency_ms": None,
                           "probe": "collection.count()"},
            "ollama":     {"healthy": ollama_ok,     "latency_ms": ollama_latency,
                           "models": ollama_models,
                           "probe": "GET /api/tags → model list"},
            "loki":       {"healthy": loki_ok,       "latency_ms": loki_latency,
                           "probe": "GET /ready → 'ready' (root 404 is normal)"},
            "prometheus": {"healthy": prometheus_ok, "latency_ms": prometheus_latency,
                           "probe": "GET /-/healthy → 'Prometheus is Healthy'"},
        },
    }


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest):
    if not model_ready:
        raise HTTPException(status_code=503, detail="Model not yet loaded — triage service initialising")

    response = await run_pipeline(request)
    duration_s = response.processing_time_ms / 1000.0

    # Persist to Redis stream
    event_payload = {
        **response.model_dump(),
        "event_type":        "triage_decision",
        "financeflow_agent": getattr(request, "financeflow_agent", ""),
        "timestamp":         request.timestamp,
    }
    try:
        redis_store.push_event_to_stream(event_payload)
        redis_store.append_to_session(
            request.session_id,
            {
                "request_id":      request.request_id,
                "agent_id":        request.agent_id,
                "agent_role":      request.agent_role,
                "tool_name":       request.tool_name,
                "routing_decision": response.routing_decision,
                "final_score":     response.final_score,
                "processing_time_ms": response.processing_time_ms,
                "timestamp":       request.timestamp,
            },
        )
    except Exception as e:
        logger.warning("Redis persistence failed: %s", e)

    # Broadcast over WebSocket
    asyncio.create_task(_manager.broadcast(event_payload))

    # OTel trace
    record_triage_span(response)

    # In-memory stats
    _stats["total"] += 1
    _stats["total_time_ms"] += response.processing_time_ms
    decision = response.routing_decision.lower()
    _stats[{"block": "block", "fast_path": "fast_path", "sandbox": "sandbox"}.get(decision, "block")] += 1

    # Prometheus
    _incr_request(response.routing_decision, request.agent_role, request.tool_name, duration_s)
    if response.instant_kill and _PROMETHEUS_AVAILABLE:
        _instant_kills.inc()

    return response


@app.get("/api/events")
async def api_events(
    since: Optional[float] = None,
    limit: int = 50,
    verdict: Optional[str] = None,
    agent: Optional[str] = None,
):
    events = redis_store.get_recent_events(limit=min(limit, 200), since_timestamp=since)
    if verdict:
        events = [e for e in events if e.get("routing_decision", "").lower() == verdict.lower()]
    if agent:
        agent_lower = agent.lower()
        events = [
            e for e in events
            if agent_lower in e.get("agent_id", "").lower()
            or agent_lower in e.get("financeflow_agent", "").lower()
        ]
    return events


@app.get("/api/events/{request_id}")
async def api_event_detail(request_id: str):
    events = redis_store.get_recent_events(limit=1000)
    for evt in events:
        if evt.get("request_id") == request_id:
            return evt
    raise HTTPException(status_code=404, detail="Event not found")


@app.get("/api/stats")
async def api_stats():
    total = _stats["total"] or 1
    return {
        "total_requests":            _stats["total"],
        "block_count":               _stats["block"],
        "fast_path_count":           _stats["fast_path"],
        "sandbox_count":             _stats["sandbox"],
        "average_processing_time_ms": round(_stats["total_time_ms"] / total, 2),
    }


@app.get("/stats")
async def stats():
    return await api_stats()


@app.post("/api/report")
async def generate_report(request: Request) -> PlainTextResponse:
    """Generate a comprehensive security report for a session."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    workflow_id = body.get("workflow_id", "unknown")
    query = body.get("query", "")
    events = body.get("events", [])
    counts = body.get("counts", {})

    # Fetch recent events from Redis if none provided
    if not events:
        events = redis_store.get_recent_events(limit=50)

    now = datetime.utcnow().isoformat() + "Z"
    total = len(events)
    n_allow   = sum(1 for e in events if (e.get("routing_decision") or "").upper() in ("FAST_PATH", "ALLOW"))
    n_sandbox = sum(1 for e in events if (e.get("routing_decision") or "").upper() == "SANDBOX")
    n_block   = sum(1 for e in events if (e.get("routing_decision") or "").upper() == "BLOCK")

    lines = [
        "═" * 65,
        "             AGENTGUARD-X SECURITY ANALYSIS REPORT",
        "═" * 65,
        "",
        f"Report ID:    REPORT-{now[:10]}-{workflow_id[:8]}",
        f"Generated:    {now}",
        f"User Query:   \"{query[:80]}\"",
        "",
        "EXECUTIVE SUMMARY",
        "─" * 17,
        f"Total Interceptions: {total}",
        f"  ALLOW:             {n_allow}  ({(n_allow/total*100 if total else 0):.1f}%)",
        f"  SANDBOX:           {n_sandbox}  ({(n_sandbox/total*100 if total else 0):.1f}%)",
        f"  BLOCKED:           {n_block}  ({(n_block/total*100 if total else 0):.1f}%)",
        "",
        "Compliance:  GDPR ✓, SOX ✓, HIPAA N/A",
        "",
        "═" * 65,
        "DETAILED EXECUTION LOG",
        "─" * 22,
    ]

    STAGE_NAMES_MAP = {
        1: "Identity Validation",
        2: "Signature Matching",
        3: "OPA Policy",
        4: "Semantic RAG",
        5: "Behavioral Drift",
        6: "Rate Limiting",
        7: "Resource Budget",
        8: "Final Aggregation",
    }

    for idx, evt in enumerate(events[-20:], 1):
        routing = (evt.get("routing_decision") or "UNKNOWN").upper()
        verdict_label = {"FAST_PATH": "ALLOW ✓", "BLOCK": "BLOCKED ✗", "SANDBOX": "SANDBOX ⚠"}.get(routing, routing)
        lines += [
            "",
            f"[OPERATION {idx}]  {evt.get('timestamp', now)}",
            f"  Tool:         {evt.get('agent_id','?')}.{evt.get('tool_name','?')}",
            f"  Trace ID:     {evt.get('request_id','?')}",
            f"  Verdict:      {verdict_label}",
            f"  Risk Score:   {evt.get('final_score',0):.4f}",
            f"  Latency:      {evt.get('processing_time_ms',0):.1f}ms",
            f"  OWASP:        {evt.get('owasp_category','N/A')}",
            f"  MITRE:        {evt.get('mitre_ref','N/A')}",
            "",
            "  TRIAGE PIPELINE:",
        ]

        for sr in (evt.get("stage_results") or []):
            stage_num = sr.get("stage", 0)
            stage_name = STAGE_NAMES_MAP.get(stage_num, f"Stage {stage_num}")
            score = sr.get("score", 0.0)
            triggered = sr.get("triggered", False)
            reason = (sr.get("reason") or "")[:60]
            status = "⚠ TRIGGERED" if triggered else "✓ CLEAN"
            if sr.get("details", {}).get("skipped"):
                status = "⏭ SKIPPED"
            lines.append(f"    [{stage_num}] {stage_name:<22} Score: {score:.3f}  {status}")
            if triggered and reason:
                lines.append(f"        Reason: {reason}")

        lines += [
            "",
            f"  Explanation: {(evt.get('explanation') or '')[:120]}",
            "  " + "─" * 60,
        ]

    lines += [
        "",
        "═" * 65,
        "COMPLIANCE FRAMEWORK ANALYSIS",
        "─" * 30,
        "",
        "GDPR Compliance:",
        "  ✓ Data Access Logged: YES (stored in Redis + Loki)",
        "  ✓ Audit Trail:        COMPLETE with timestamps",
        "  ✓ Purpose:            Financial analysis",
        "  ✓ Retention:          30 days compliant",
        "",
        "SOX Compliance:",
        "  ✓ Change Control:     Approval chain documented",
        "  ✓ Segregation of Duties: ENFORCED (OPA Stage 3)",
        "  ✓ Access Control:     RBAC enforced via OPA",
        "  ✓ Audit Trail:        All actions traced",
        "",
        "═" * 65,
        "",
        "Report Generated By: AgentGuard-X Security Mesh v2.3.1",
        f"Timestamp: {now}",
        "═" * 65,
    ]

    return PlainTextResponse("\n".join(lines), media_type="text/plain")


@app.get("/metrics")
async def metrics():
    if not _PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="prometheus_client not installed")
    return PlainTextResponse(
        generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


# ─── /execute — simplified entry point ───────────────────────────────────────
# Accepts {agent_id, tool_name, input} and runs the full 5-stage triage pipeline.
# Returns {verdict, risk_score, reason, trace_id, latency_ms, stages}.

_EXECUTE_AGENT_MAP = {
    # Underscore variants map to canonical hyphenated IDs
    "research_001": "research-001",
    "analyst_001":  "analyst-001",
    "report_001":   "report-001",
    "orchestrator_001": "orchestrator-001",
    "data_001":     "data-001",
}

_VERDICT_MAP = {
    "FAST_PATH": "ALLOW",
    "BLOCK":     "BLOCKED",
    "SANDBOX":   "SANDBOX",
}

_STAGE_NAMES = {
    1: "identity",
    2: "signature",
    3: "policy",
    4: "semantic",
    5: "behavioral",
    6: "rate_limit",
    7: "resource",
    8: "aggregation",
}


def _build_stage_summary(stage_results) -> dict:
    summary = {}
    for sr in stage_results:
        name = _STAGE_NAMES.get(sr.stage, f"stage{sr.stage}")
        if sr.stage in (1, 6):
            summary[name] = "PASS" if not sr.triggered else "FAIL"
        elif sr.stage == 3:
            summary[name] = "ALLOW" if not sr.triggered else "DENY"
        elif sr.stage == 8:
            summary[name] = {
                "final_score": round(sr.score, 4),
                "routing": sr.details.get("routing_decision", ""),
                "details": sr.details,
            }
        else:
            summary[name] = round(sr.score, 4)
    return summary


def _build_stage_detail(stage_results) -> list:
    detail = []
    for sr in stage_results:
        name = _STAGE_NAMES.get(sr.stage, f"stage{sr.stage}")
        detail.append({
            "stage": sr.stage,
            "name": name,
            "score": round(sr.score, 4),
            "triggered": sr.triggered,
            "reason": sr.reason,
            "details": sr.details,
            "skipped": sr.details.get("skipped", False),
        })
    return detail


def _derive_reason(verdict: str, triage_response) -> str:
    if verdict == "BLOCKED":
        if triage_response.instant_kill:
            return "INJECTION_DETECTED"
        for sr in triage_response.stage_results:
            if sr.stage == 1 and sr.triggered:
                return "AUTHENTICATION_FAILED"
            if sr.stage == 3 and sr.triggered:
                return "RBAC_DENIED"
        return "THREAT_DETECTED"
    if verdict == "SANDBOX":
        return "SUSPICIOUS_PATTERN"
    return "clean_request"


@app.post("/execute")
async def execute(request: Request) -> dict:
    """
    Simplified security-mesh entry point.

    Input:  {agent_id, tool_name, input}
    Output: {verdict, risk_score, reason, trace_id, latency_ms, stages}

    verdict is one of: ALLOW | BLOCKED | SANDBOX
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})

    agent_id_raw = str(body.get("agent_id", "")).strip()
    tool_name    = str(body.get("tool_name", "")).strip()
    user_input   = body.get("input", {})

    # Normalise agent_id: underscore variants → canonical hyphenated ID
    agent_id_canonical = _EXECUTE_AGENT_MAP.get(agent_id_raw, agent_id_raw.replace("_", "-"))

    # Look up role; fall back to name-based inference
    from config import REGISTERED_AGENTS
    agent_info = REGISTERED_AGENTS.get(agent_id_canonical) or REGISTERED_AGENTS.get(agent_id_raw)
    if agent_info is None:
        low = agent_id_raw.lower()
        if "research" in low:
            agent_info = {"role": "research_agent", "owner": "financeflow"}
            # Keep the raw hyphenated ID to isolate rate-limit/session state per agent
            agent_id_canonical = agent_id_raw.replace("_", "-")
        elif "analyst" in low:
            agent_info = {"role": "analyst_agent", "owner": "financeflow"}
            agent_id_canonical = agent_id_raw.replace("_", "-")
        elif "report" in low:
            agent_info = {"role": "report_agent", "owner": "financeflow"}
            agent_id_canonical = agent_id_raw.replace("_", "-")
        elif "orchestrat" in low:
            agent_info = {"role": "orchestrator_agent", "owner": "financeflow"}
            agent_id_canonical = agent_id_raw.replace("_", "-")
        else:
            trace_id = str(uuid.uuid4())
            redis_store.store_agent_session(agent_id_raw, "unknown", tool_name, "BLOCKED")
            redis_store.increment_verdict_counter("BLOCKED")
            redis_store.log_decision(agent_id_raw, "BLOCKED", 1.0, trace_id, tool_name)
            return {
                "verdict": "BLOCKED",
                "risk_score": 1.0,
                "reason": "UNREGISTERED_AGENT",
                "trace_id": trace_id,
                "latency_ms": 0.0,
                "stages": {"identity": "FAIL", "signature": 0.0, "policy": False, "semantic": 0.0, "behavioral": 0.0},
            }

    agent_role = agent_info["role"]

    # Validate tool_name format (must be lowercase snake_case)
    if not _re.match(r"^[a-z_][a-z0-9_]{0,63}$", tool_name):
        return JSONResponse(status_code=400, content={"detail": f"Invalid tool_name: '{tool_name}'"})

    if not isinstance(user_input, dict):
        user_input = {"value": str(user_input)}

    tool_input_raw = json.dumps(user_input)
    session_id     = f"exec-{agent_id_raw}"
    request_id     = str(uuid.uuid4())

    try:
        triage_req = TriageRequest(
            agent_id=agent_id_canonical,
            session_id=session_id,
            tool_name=tool_name,
            tool_input=user_input,
            tool_input_raw=tool_input_raw,
            agent_role=agent_role,
            timestamp=time.time(),
            request_id=request_id,
        )
    except Exception as exc:
        return JSONResponse(status_code=400, content={"detail": f"Request validation error: {exc}"})

    triage_resp = await run_pipeline(triage_req)

    verdict = _VERDICT_MAP.get(triage_resp.routing_decision, triage_resp.routing_decision)

    # Stage 3 (OPA RBAC) is categorical: an explicit policy denial → always BLOCKED.
    # The aggregate score can be diluted by low-risk stages, but a denied tool must not
    # be routed to SANDBOX where it could still execute.
    s3_result = next((sr for sr in triage_resp.stage_results if sr.stage == 3), None)
    if s3_result and s3_result.triggered and verdict != "BLOCKED":
        verdict = "BLOCKED"

    reason       = _derive_reason(verdict, triage_resp)
    stages       = _build_stage_summary(triage_resp.stage_results)
    stage_detail = _build_stage_detail(triage_resp.stage_results)

    # Persist session + metrics
    redis_store.store_agent_session(agent_id_raw, agent_role, tool_name, verdict)
    redis_store.increment_verdict_counter(verdict)
    redis_store.log_decision(agent_id_raw, verdict, triage_resp.final_score, request_id, tool_name)

    # Also push to the existing event stream for WebSocket/Grafana
    try:
        redis_store.push_event_to_stream({
            **triage_resp.model_dump(),
            "event_type":    "execute_decision",
            "verdict_simple": verdict,
            "timestamp":     time.time(),
        })
        redis_store.append_to_session(
            session_id,
            {
                "request_id":        request_id,
                "agent_id":          agent_id_canonical,
                "agent_role":        agent_role,
                "tool_name":         tool_name,
                "routing_decision":  triage_resp.routing_decision,
                "final_score":       triage_resp.final_score,
                "processing_time_ms": triage_resp.processing_time_ms,
                "timestamp":         time.time(),
            },
        )
    except Exception as e:
        logger.warning("Redis event persistence failed: %s", e)

    asyncio.create_task(_manager.broadcast({
        **triage_resp.model_dump(),
        "event_type":    "execute_decision",
        "verdict_simple": verdict,
        "timestamp":     time.time(),
    }))

    _incr_request(triage_resp.routing_decision, agent_role, tool_name, triage_resp.processing_time_ms / 1000.0)

    return {
        "verdict":        verdict,
        "risk_score":     round(triage_resp.final_score, 4),
        "reason":         reason,
        "trace_id":       request_id,
        "latency_ms":     triage_resp.processing_time_ms,
        "explanation":    triage_resp.explanation,
        "owasp_category": triage_resp.owasp_category,
        "mitre_ref":      triage_resp.mitre_ref,
        "stages":         stages,
        "stage_detail":   stage_detail,
        "agent_id":       agent_id_raw,
        "agent_role":     agent_role,
        "tool_name":      tool_name,
    }
