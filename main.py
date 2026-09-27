from __future__ import annotations

import asyncio
import importlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from rag import query_rag

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
S3_BUCKET = os.getenv("S3_BUCKET", "indexdata")
S3_FILES = {
    DATA_DIR / "faiss_index.index": os.getenv("S3_INDEX_KEY", "faiss_index.index"),
    DATA_DIR / "processed_docs.json": os.getenv("S3_DOCUMENTS_KEY", "processed_docs.json"),
}
LLM_TIMEOUT_SECONDS = 5.0
LLM_MAX_RETRIES = 2
offline_ai_enabled = os.getenv("OFFLINE_AI_ENABLED", "false").lower() == "true"

app = FastAPI(title="Farmer AI Assistant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(PROJECT_DIR / "index.html")


@app.get("/app.js", include_in_schema=False)
async def frontend_script() -> FileResponse:
    return FileResponse(PROJECT_DIR / "app.js", media_type="application/javascript")


@app.get("/style.css", include_in_schema=False)
async def frontend_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "style.css", media_type="text/css")


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain text")
        return value


class AskResponse(BaseModel):
    success: bool = True
    answer: str
    mode: str
    source_docs: list[str]


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


def _download_missing_files() -> None:
    missing = [(path, key) for path, key in S3_FILES.items() if not path.is_file()]
    if not missing:
        logger.info("RAG cache is present; skipping S3 downloads")
        return
    endpoint = os.getenv("AWS_ENDPOINT_URL_S3")
    if not endpoint:
        logger.warning("RAG cache is incomplete and AWS_ENDPOINT_URL_S3 is not configured")
        return
    try:
        boto3 = importlib.import_module("boto3")

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for destination, key in missing:
            temporary = destination.with_suffix(destination.suffix + ".part")
            logger.info("Streaming %s from S3", key)
            response = client.get_object(Bucket=S3_BUCKET, Key=key)
            with temporary.open("wb") as output:
                for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
            temporary.replace(destination)
    except Exception:
        logger.exception("Unable to download RAG resources from S3")


@app.on_event("startup")
async def startup() -> None:
    await asyncio.to_thread(_download_missing_files)


def _local_answer(query: str) -> str:
    lower = query.lower()
    if any(word in lower for word in ("disease", "yellow", "spot")):
        return "Check affected leaves, isolate badly affected plants, and consult a local agriculture officer for a confirmed diagnosis."
    if "fertilizer" in lower or "fertiliser" in lower:
        return "Avoid applying fertilizer without a soil test. Use crop and soil details for a specific recommendation."
    return "Local fallback is active. Ask about crops, diseases, soil, weather, or fertilizers when the service is available."


def _generate_with_gemini(query: str, results: list[str]) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(query_rag.llm_generate, query, results)
    try:
        return future.result(timeout=LLM_TIMEOUT_SECONDS)
    finally:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)


def generate_answer(query: str, results: list[str]) -> tuple[str, str]:
    if offline_ai_enabled:
        return _local_answer(query), "fallback"
    if not results:
        logger.info("Mode used: fallback; no RAG documents available")
        return _local_answer(query), "fallback"
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            answer = _generate_with_gemini(query, results)
            logger.info("Mode used: rag+llm; attempt=%d", attempt + 1)
            return answer, "rag+llm"
        except (FutureTimeoutError, Exception) as exc:
            logger.warning("Gemini attempt %d failed: %s", attempt + 1, exc)
    if results:
        logger.info("Mode used: rag")
        return query_rag.rag_only_answer(results), "rag"
    logger.info("Mode used: fallback")
    return _local_answer(query), "fallback"


@app.get("/health")
async def health_check() -> dict[str, Any]:
    return {"status": "ok", "rag": query_rag.status(), "offline_ai_enabled": offline_ai_enabled}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"success": False, "error": str(exc)})


@app.post("/ask", response_model=AskResponse | ErrorResponse)
async def ask(request: AskRequest) -> AskResponse | JSONResponse:
    query = request.query.strip()
    logger.info("Query: %s", query)
    try:
        results = await asyncio.to_thread(query_rag.search, query, 10)
        answer, mode = await asyncio.to_thread(generate_answer, query, results)
        return AskResponse(answer=answer, mode=mode, source_docs=results[:3])
    except Exception:
        logger.exception("Request failed")
        return JSONResponse(status_code=500, content={"success": False, "error": "Unable to answer this query right now."})