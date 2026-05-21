import asyncio
import logging
import time
import traceback
from contextlib import asynccontextmanager

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

_stats = {
    "total": 0,
    "block": 0,
    "fast_path": 0,
    "sandbox": 0,
    "total_time_ms": 0.0,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AgentGuard-X triage service starting up...")
    init_otel()
    # Initialize ChromaDB and load embedding model at startup
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, knowledge_base.initialize)
    logger.info("AgentGuard-X triage service ready.")
    yield
    logger.info("AgentGuard-X triage service shutting down.")


app = FastAPI(title="AgentGuard-X Triage Engine", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review_router)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    logger.error("Unhandled exception on %s %s\n%s", request.method, request.url, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "exception_type": type(exc).__name__},
    )


@app.get("/health")
async def health():
    redis_ok = redis_store.is_healthy()
    chromadb_ok = knowledge_base.is_healthy()

    opa_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(OPA_URL + "/health")
            opa_ok = r.status_code == 200
    except Exception:
        pass

    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(OLLAMA_BASE_URL + "/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "components": {
            "redis": redis_ok,
            "opa": opa_ok,
            "chromadb": chromadb_ok,
            "ollama": ollama_ok,
        },
    }


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest):
    response = await run_pipeline(request)

    record_triage_span(response)

    _stats["total"] += 1
    _stats["total_time_ms"] += response.processing_time_ms
    decision = response.routing_decision.lower()
    if decision == "block":
        _stats["block"] += 1
    elif decision == "fast_path":
        _stats["fast_path"] += 1
    elif decision == "sandbox":
        _stats["sandbox"] += 1

    return response


@app.get("/stats")
async def stats():
    total = _stats["total"] or 1
    return {
        "total_requests": _stats["total"],
        "block_count": _stats["block"],
        "fast_path_count": _stats["fast_path"],
        "sandbox_count": _stats["sandbox"],
        "average_processing_time_ms": round(_stats["total_time_ms"] / total, 2),
    }
