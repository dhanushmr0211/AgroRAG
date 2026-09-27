"""Lazy FAISS retrieval for the Farmer AI API."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)
INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "faiss_index.index"
DOCUMENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed_docs.json"
MODEL_NAME = "all-MiniLM-L6-v2"
_load_lock = threading.Lock()
_index: Any = None
_documents: list[str] = []
_model: Any = None
_load_error: str | None = None


def _load_resources() -> bool:
    global _index, _documents, _model, _load_error
    if _index is not None and _model is not None:
        return True
    with _load_lock:
        if _index is not None and _model is not None:
            return True
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            if not INDEX_PATH.is_file() or not DOCUMENTS_PATH.is_file():
                raise FileNotFoundError("RAG index or processed documents are missing")
            with DOCUMENTS_PATH.open("r", encoding="utf-8") as file:
                loaded_documents = json.load(file)
            if not isinstance(loaded_documents, list):
                raise ValueError("processed documents must be a JSON list")
            _index = faiss.read_index(str(INDEX_PATH))
            _documents = [str(document) for document in loaded_documents]
            _model = SentenceTransformer(MODEL_NAME)
            _load_error = None
            logger.info("Loaded RAG resources: %d documents", len(_documents))
            return True
        except Exception as exc:
            _load_error = str(exc)
            logger.warning("RAG resources unavailable: %s", exc)
            return False


def status() -> dict[str, Any]:
    return {"ready": _index is not None and _model is not None, "documents": len(_documents), "error": _load_error}


def search(query: str, k: int = 10) -> list[str]:
    if not _load_resources():
        return []
    query_lower = query.lower()
    intent = "general"
    if any(word in query_lower for word in ("disease", "yellow", "spots", "infection")):
        intent = "disease"
    elif "fertilizer" in query_lower or "fertiliser" in query_lower:
        intent = "fertilizer"
    elif "soil" in query_lower:
        intent = "soil"
    query_embedding = np.asarray(_model.encode([query]), dtype="float32")
    _, indices = _index.search(query_embedding, min(max(k * 5, k), len(_documents)))
    query_terms = set(re.findall(r"[a-z0-9]+", query_lower))
    candidates: list[tuple[int, int, str]] = []
    for position, document_index in enumerate(indices[0]):
        if document_index < 0 or document_index >= len(_documents):
            continue
        document = _documents[document_index]
        document_lower = document.lower()
        if intent != "general" and f"type: {intent}" not in document_lower:
            continue
        if "rice" in query_lower and "crop: rice" not in document_lower:
            continue
        if "tomato" in query_lower and "crop: tomato" not in document_lower:
            continue
        document_terms = set(re.findall(r"[a-z0-9]+", document_lower))
        overlap = len(query_terms & document_terms)
        boost = 2 if "rice" in query_terms and "rice" in document_lower else 0
        candidates.append((overlap + boost, position, document))
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    return [document for _, _, document in candidates[:k]]


def rag_only_answer(results: list[str]) -> str:
    return "\n\n".join(results[:3]) or "The farm knowledge base is not available right now. Please try again shortly."


def llm_generate(query: str, context_docs: list[str]) -> str:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    context = "\n".join(context_docs)
    response = genai.Client(api_key=api_key).models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=("You are an agricultural assistant. Use only this context. If it does not answer the question, say 'Not enough data'. "
                  f"Be concise and practical.\n\nContext:\n{context}\n\nQuestion:\n{query}"),
    )
    answer = getattr(response, "text", None)
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Gemini returned an empty response")
    return answer.strip()


def rag_pipeline(query: str) -> str:
    return rag_only_answer(search(query))


if __name__ == "__main__":
    print(rag_pipeline(input("Enter your question: ")))