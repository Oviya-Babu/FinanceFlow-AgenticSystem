"""
FinanceFlow consolidated FastAPI service — single source of truth.

Endpoints:
  POST /chat                      — main chatbot (autonomous agent)
  GET  /ws/events                 — WebSocket live event stream
  GET  /health                    — correct service health probes
  POST /api/upload                — file upload for per-session RAG
  DELETE /api/upload/{sid}/{did}  — remove uploaded file chip
  GET  /api/uploads/{session_id}  — list uploaded files for session
  GET  /api/report/{workflow_id}  — retrieve all three reports
  GET  /api/report/{wid}/text     — plaintext download of all three reports
  GET  /outputs/{filename}        — serve artifact files
  GET  /                          — chatbot frontend
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# Path setup — find AgentGuard-X and financeflow
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT / "AgentGuard-X"))
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from financeflow.orchestrator import run_query
from financeflow.rag_memory import (
    list_uploaded_files,
    query_uploads,
    remove_uploaded_file,
    upload_document,
)
from financeflow.report_generator import (
    build_all_reports,
    format_text_report,
)
from financeflow.tool_registry import AGENTGUARD_URL, OUTPUTS_DIR

AGENTGUARD_WS = os.getenv("AGENTGUARD_WS", "ws://localhost:8001/ws/events")

# ─── In-memory workflow store ─────────────────────────────────────────────────
# Maps workflow_id → {result, reports, events[]}
_workflows: dict[str, dict] = {}
_workflow_events: dict[str, list] = {}

# ─── WebSocket manager ────────────────────────────────────────────────────────
class _ConnMgr:
    def __init__(self):
        self._active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket):
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


_mgr = _ConnMgr()

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FinanceFlow service starting...")
    yield
    logger.info("FinanceFlow service shutting down.")


app = FastAPI(title="FinanceFlow AI Platform", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve artifact files
if OUTPUTS_DIR.is_dir():
    app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# Serve chatbot frontend
_FRONTEND_DIR = _ROOT / "frontend" / "chatbot"
if _FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIR)), name="assets")


@app.exception_handler(Exception)
async def _global_exc(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ─── Frontend ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    candidates = [
        _FRONTEND_DIR / "index.html",
        _ROOT / "frontend" / "chatbot.html",
        _ROOT / "frontend" / "index.html",
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(str(path))
    return HTMLResponse("<h1>FinanceFlow AI Platform</h1><p>Frontend not found</p>")


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    agentguard_ok = False
    agentguard_latency = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            t0 = time.time()
            r = await c.get(f"{AGENTGUARD_URL}/health")
            agentguard_latency = round((time.time() - t0) * 1000, 1)
            agentguard_ok = r.status_code == 200 and r.json().get("status") in ("ok", "degraded")
    except Exception:
        pass

    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get("http://localhost:11434/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass

    # Redis — check via AgentGuard-X health response
    redis_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{AGENTGUARD_URL}/health")
            if r.status_code == 200:
                redis_ok = r.json().get("components", {}).get("redis", {}).get("healthy", False)
    except Exception:
        pass

    return {
        "status": "ok" if agentguard_ok else "degraded",
        "service": "financeflow",
        "components": {
            "agentguard_x":  {"healthy": agentguard_ok, "latency_ms": agentguard_latency,
                               "probe": f"GET {AGENTGUARD_URL}/health"},
            "ollama":        {"healthy": ollama_ok,
                               "probe": "GET http://localhost:11434/api/tags"},
            "redis":         {"healthy": redis_ok,
                               "probe": "redis-cli ping → PONG (via AgentGuard-X)"},
        },
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await _mgr.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _mgr.disconnect(websocket)


# ─── POST /chat — main chatbot endpoint ──────────────────────────────────────
@app.post("/chat")
async def chat(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})

    query = str(body.get("query", "")).strip()
    if not query:
        return JSONResponse(status_code=400, content={"detail": "query must not be empty"})

    session_id = str(body.get("session_id", f"ff-{uuid.uuid4().hex[:8]}"))
    workflow_id = f"wf-{uuid.uuid4().hex[:10]}"

    # Gather any uploaded context for RAG grounding
    upload_hits = query_uploads(session_id, query, top_k=3)
    uploaded_context = "\n\n".join(h["document"] for h in upload_hits) if upload_hits else ""

    events_list: list[dict] = []
    _workflow_events[workflow_id] = events_list

    async def emit(event: dict):
        event["workflow_id"] = workflow_id
        event["timestamp"]   = time.time()
        events_list.append(event)
        await _mgr.broadcast(event)

    # Run the autonomous orchestrator
    result = await run_query(query, session_id, emit, uploaded_context)

    # Build three reports
    reports = build_all_reports(result)
    _workflows[workflow_id] = {
        "result":  result.to_dict(),
        "reports": reports,
        "query":   query,
        "session_id": session_id,
    }

    # Tally verdict counts
    security_events = result.security_events
    allow_count   = sum(1 for e in security_events if e.get("verdict") == "ALLOW")
    sandbox_count = sum(1 for e in security_events if e.get("verdict") == "SANDBOX")
    block_count   = sum(1 for e in security_events if e.get("verdict") in ("BLOCK", "BLOCKED"))

    # Collect primary result content for the UI
    primary_output = _extract_primary_output(result)

    return JSONResponse({
        "workflow_id":  workflow_id,
        "session_id":   session_id,
        "status":       result.status,
        "query":        query,
        "result":       primary_output,
        "artifacts":    [
            {"path": a, "url": f"/outputs/{Path(a).name}", "name": Path(a).name}
            for a in result.artifacts
        ],
        "security_summary": {
            "total":   len(security_events),
            "allow":   allow_count,
            "sandbox": sandbox_count,
            "block":   block_count,
        },
        "timing_ms":    result.total_ms,
        "reports_url":  f"/api/report/{workflow_id}",
    })


def _extract_primary_output(result) -> str:
    """Pull the most meaningful output from the execution result for the UI."""
    if not result.outputs:
        if result.status == "blocked":
            blocked = next(
                (s for s in result.graph.steps if s.status == "blocked"), None
            )
            if blocked:
                return (
                    f"⚠️ Execution stopped.\n\n"
                    f"Step '{blocked.description}' was blocked by AgentGuard-X.\n\n"
                    f"Reason: {blocked.error}\n"
                    f"Risk score: {blocked.risk_score:.4f}\n\n"
                    "A security report has been generated. See 'View Security Details'."
                )
        return "No output generated."

    # Prefer the last completed step's output
    parts = []
    for out in result.outputs:
        data = out.get("output", {}).get("data", "")
        source = out.get("output", {}).get("source", "unknown")
        tool = out.get("tool", "")

        label = f"[{source}]" if source != "real_local" else ""

        if isinstance(data, dict):
            # Format financial data nicely
            if "symbol" in data:
                parts.append(
                    f"**{data.get('shortName', data.get('symbol', ''))}** ({data.get('symbol', '')})\n"
                    f"Price: ${data.get('currentPrice', 'N/A')} | "
                    f"Market Cap: {_fmt_num(data.get('marketCap'))} | "
                    f"P/E: {data.get('trailingPE', 'N/A')}\n"
                    f"{data.get('summary', '')}\n{label}"
                )
            elif "answer" in data:
                parts.append(f"{data['answer']}\n{label}")
            elif "result" in data:
                parts.append(f"{data['result']}\n{label}")
            elif "title" in data and "pdf_path" in data:
                parts.append(
                    f"**Report generated:** {data['title']}\n"
                    f"PDF: {data.get('pdf_path', 'N/A')}\n{label}"
                )
            elif "status" in data:
                parts.append(f"{data.get('status', str(data))}\n{label}")
            else:
                parts.append(f"{json.dumps(data, indent=2)[:400]}\n{label}")
        else:
            parts.append(f"{str(data)[:400]}\n{label}")

    return "\n\n---\n\n".join(parts)


def _fmt_num(n) -> str:
    if n is None:
        return "N/A"
    if n >= 1e12:
        return f"${n/1e12:.1f}T"
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    return f"${n:,.0f}"


# ─── File upload / movable RAG ────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(default="ff-default"),
) -> JSONResponse:
    content_bytes = await file.read()
    # Try UTF-8 decode; handle binary PDFs gracefully
    try:
        content = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        content = str(content_bytes)

    result = upload_document(session_id, content, file.filename or "upload")
    return JSONResponse(result)


@app.get("/api/uploads/{session_id}")
async def list_uploads(session_id: str) -> JSONResponse:
    return JSONResponse(list_uploaded_files(session_id))


@app.delete("/api/upload/{session_id}/{doc_id}")
async def delete_upload(session_id: str, doc_id: str) -> JSONResponse:
    ok = remove_uploaded_file(session_id, doc_id)
    return JSONResponse({"deleted": ok, "doc_id": doc_id})


# ─── Reports ─────────────────────────────────────────────────────────────────
@app.get("/api/report/{workflow_id}")
async def get_report(workflow_id: str) -> JSONResponse:
    wf = _workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return JSONResponse(wf["reports"])


@app.get("/api/report/{workflow_id}/text", response_class=PlainTextResponse)
async def get_report_text(workflow_id: str) -> PlainTextResponse:
    wf = _workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    text = format_text_report(wf["reports"])
    return PlainTextResponse(text, media_type="text/plain")


# ─── Thin runner entry for scripted scenarios ─────────────────────────────────
@app.post("/api/scenario")
async def run_scenario(request: Request) -> JSONResponse:
    """Programmatic entry for scripted demo scenarios (matches runner.py)."""
    return await chat(request)
