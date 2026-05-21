import logging
import uuid as _uuid_mod
from typing import List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CHROMA_COLLECTION_NAME, EMBEDDING_MODEL, RAG_TOP_K

logger = logging.getLogger(__name__)

_model = None
_collection = None
_chroma_client = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SentenceTransformer model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("SentenceTransformer model loaded.")
    return _model


def _get_collection():
    global _collection, _chroma_client
    if _collection is None:
        import chromadb
        # Use EphemeralClient for in-process usage (chromadb 0.4+/0.5+)
        try:
            _chroma_client = chromadb.EphemeralClient()
        except AttributeError:
            _chroma_client = chromadb.Client()
        _collection = _chroma_client.get_or_create_collection(
            CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def initialize(seed_entries: Optional[list] = None) -> None:
    col = _get_collection()
    _get_model()

    if col.count() > 0:
        logger.info("ChromaDB collection already seeded (%d entries). Skipping.", col.count())
        return

    if seed_entries is None:
        from rag.seed_data import THREAT_ENTRIES
        seed_entries = THREAT_ENTRIES

    logger.info("Seeding ChromaDB with %d threat entries...", len(seed_entries))
    model = _get_model()

    texts = [e["description"] for e in seed_entries]
    embeddings = model.encode(texts).tolist()
    ids = [e["id"] for e in seed_entries]
    metadatas = [
        {
            "title": e["title"],
            "severity": e["severity"],
            "owasp_ref": e["owasp_ref"],
            "mitre_ref": e["mitre_ref"],
            "false_positive_rate": e["false_positive_rate"],
            "recommended_action": e["recommended_action"],
        }
        for e in seed_entries
    ]

    col.add(
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
        ids=ids,
    )
    logger.info("ChromaDB seeding complete.")


def query(text: str, top_k: int = RAG_TOP_K) -> List[dict]:
    try:
        col = _get_collection()
        model = _get_model()
        embedding = model.encode([text]).tolist()
        results = col.query(
            query_embeddings=embedding,
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "similarity": 1.0 - results["distances"][0][i],
            })
        return hits
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []


def add_entry(entry: dict) -> None:
    try:
        col = _get_collection()
        model = _get_model()
        text = entry.get("description", entry.get("analyst_notes", str(entry)))
        embedding = model.encode([text]).tolist()
        entry_id = entry.get("id", f"analyst_{_uuid_mod.uuid4().hex[:8]}")
        col.add(
            embeddings=embedding,
            documents=[text],
            metadatas=[{
                "title": entry.get("title", "Analyst Entry"),
                "severity": entry.get("severity", "medium"),
                "owasp_ref": entry.get("owasp_ref", ""),
                "mitre_ref": entry.get("mitre_ref", ""),
                "false_positive_rate": entry.get("false_positive_rate", 0.1),
                "recommended_action": entry.get("recommended_action", "monitor"),
            }],
            ids=[entry_id],
        )
    except Exception as e:
        logger.error("ChromaDB add_entry failed: %s", e)


def is_healthy() -> bool:
    try:
        _get_collection()
        return True
    except Exception:
        return False
