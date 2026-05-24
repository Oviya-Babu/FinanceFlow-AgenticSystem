"""
FinanceFlow RAG memory — three distinct ChromaDB collections.

threat_patterns   — AgentGuard-X threats (owned by AgentGuard-X; READ-ONLY from here)
company_policies  — FinanceFlow company policy docs
user_uploads_<sid> — Per-session user-uploaded documents (movable RAG)

Collections are NEVER cross-contaminated.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_policy_collection = None
_upload_collections: dict[str, object] = {}


# ─── Injection patterns to scan uploaded content ─────────────────────────────
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|your)\s+instructions",
    r"disregard\s+(all|your|previous)",
    r"override\s+(your\s+)?system\s+prompt",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"\[\[system\]\]",
    r"<\|im_start\|>",
    r"new\s+instructions\s*:",
    r"forget\s+(everything|all)",
    r"act\s+as\s+(if\s+you\s+are|a\s+)",
]
_INJ_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _get_client():
    global _client
    if _client is None:
        try:
            import chromadb
            try:
                _client = chromadb.EphemeralClient()
            except AttributeError:
                _client = chromadb.Client()
        except ImportError:
            logger.warning("chromadb not available — RAG memory disabled")
            _client = None
    return _client


def _get_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return _FallbackModel()


class _FallbackModel:
    def encode(self, texts):
        result = []
        for text in texts:
            v = sum(ord(c) for c in text)
            result.append([((v + i * 31) % 997) / 997.0 for i in range(64)])
        return result


_model = None

def _model_instance():
    global _model
    if _model is None:
        _model = _get_model()
    return _model


def _embed(texts: list[str]) -> list[list[float]]:
    m = _model_instance()
    vecs = m.encode(texts)
    return [v.tolist() if hasattr(v, "tolist") else v for v in vecs]


# ─── Company policies collection ─────────────────────────────────────────────

_POLICY_DOCS = [
    {"id": "pol-001", "text": "All external emails must be approved by compliance before sending.",
     "category": "communication"},
    {"id": "pol-002", "text": "Customer financial records are confidential and access is restricted to authorized analysts.",
     "category": "data_privacy"},
    {"id": "pol-003", "text": "All financial reports must include a risk disclosure statement.",
     "category": "reporting"},
    {"id": "pol-004", "text": "API keys and credentials must never be included in reports or emails.",
     "category": "security"},
    {"id": "pol-005", "text": "Bulk data exports require dual authorization from a manager and compliance officer.",
     "category": "data_governance"},
]


def _get_policy_collection():
    global _policy_collection
    if _policy_collection is not None:
        return _policy_collection
    client = _get_client()
    if client is None:
        return None
    try:
        col = client.get_or_create_collection("company_policies",
                                              metadata={"hnsw:space": "cosine"})
        if col.count() == 0:
            texts = [d["text"] for d in _POLICY_DOCS]
            embeddings = _embed(texts)
            col.add(embeddings=embeddings, documents=texts,
                    metadatas=[{"category": d["category"]} for d in _POLICY_DOCS],
                    ids=[d["id"] for d in _POLICY_DOCS])
        _policy_collection = col
        return col
    except Exception as exc:
        logger.warning("Failed to init policy collection: %s", exc)
        return None


def query_policies(query: str, top_k: int = 3) -> list[dict]:
    col = _get_policy_collection()
    if col is None:
        return []
    try:
        embedding = _embed([query])
        results = col.query(query_embeddings=embedding, n_results=min(top_k, col.count()),
                            include=["documents", "metadatas", "distances"])
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": round(1.0 - results["distances"][0][i], 4),
            })
        return hits
    except Exception as exc:
        logger.warning("Policy query failed: %s", exc)
        return []


# ─── Per-session user uploads ─────────────────────────────────────────────────

def _get_upload_collection(session_id: str):
    key = f"user_uploads_{session_id}"
    if key in _upload_collections:
        return _upload_collections[key]
    client = _get_client()
    if client is None:
        return None
    try:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)[:60]
        col = client.get_or_create_collection(f"user_uploads_{safe_id}",
                                              metadata={"hnsw:space": "cosine",
                                                        "session_id": session_id})
        _upload_collections[key] = col
        return col
    except Exception as exc:
        logger.warning("Failed to get upload collection for session %s: %s", session_id, exc)
        return None


def scan_for_injection(content: str) -> dict:
    """Scan content for embedded prompt injection. Returns {clean, findings}."""
    matches = _INJ_RE.findall(content)
    if matches:
        return {"clean": False, "findings": matches,
                "redacted": _INJ_RE.sub("[REDACTED-INJECTION]", content)}
    return {"clean": True, "findings": [], "redacted": content}


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i: i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks or [text[:2000]]


def upload_document(session_id: str, content: str, filename: str) -> dict:
    """
    Chunk, injection-scan, embed, and store a document in the session's upload collection.
    Returns metadata about what was stored (or blocked if injection found).
    """
    scan = scan_for_injection(content)
    if not scan["clean"]:
        logger.warning("Injection found in uploaded file %s for session %s", filename, session_id)
        content = scan["redacted"]

    col = _get_upload_collection(session_id)
    if col is None:
        return {"status": "error", "message": "RAG storage unavailable", "filename": filename,
                "injection_found": not scan["clean"]}

    chunks = _chunk_text(content)
    doc_id = hashlib.md5(f"{session_id}:{filename}:{time.time()}".encode()).hexdigest()[:12]
    embeddings = _embed(chunks)
    ids = [f"{doc_id}_chunk{i}" for i in range(len(chunks))]
    metadatas = [{"filename": filename, "doc_id": doc_id, "chunk_index": i,
                  "session_id": session_id} for i in range(len(chunks))]
    try:
        col.add(embeddings=embeddings, documents=chunks, metadatas=metadatas, ids=ids)
        return {
            "status": "stored",
            "filename": filename,
            "doc_id": doc_id,
            "chunks": len(chunks),
            "injection_found": not scan["clean"],
            "injection_redacted": not scan["clean"],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "filename": filename,
                "injection_found": not scan["clean"]}


def query_uploads(session_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Query the user's session-specific uploaded documents."""
    col = _get_upload_collection(session_id)
    if col is None or col.count() == 0:
        return []
    try:
        embedding = _embed([query])
        n = min(top_k, col.count())
        results = col.query(query_embeddings=embedding, n_results=n,
                            include=["documents", "metadatas", "distances"])
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": round(1.0 - results["distances"][0][i], 4),
            })
        return hits
    except Exception as exc:
        logger.warning("Upload query failed for session %s: %s", session_id, exc)
        return []


def list_uploaded_files(session_id: str) -> list[dict]:
    col = _get_upload_collection(session_id)
    if col is None or col.count() == 0:
        return []
    try:
        all_items = col.get(include=["metadatas"])
        seen = {}
        for meta in all_items["metadatas"]:
            doc_id = meta.get("doc_id", "?")
            if doc_id not in seen:
                seen[doc_id] = {"doc_id": doc_id, "filename": meta.get("filename", "unknown"),
                                "session_id": session_id}
        return list(seen.values())
    except Exception as exc:
        logger.warning("List uploads failed: %s", exc)
        return []


def remove_uploaded_file(session_id: str, doc_id: str) -> bool:
    col = _get_upload_collection(session_id)
    if col is None:
        return False
    try:
        all_items = col.get(include=["metadatas"])
        ids_to_delete = [
            all_items["ids"][i]
            for i, meta in enumerate(all_items["metadatas"])
            if meta.get("doc_id") == doc_id
        ]
        if ids_to_delete:
            col.delete(ids=ids_to_delete)
        return True
    except Exception as exc:
        logger.warning("Remove upload failed: %s", exc)
        return False
