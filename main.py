import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from rag.query_rag import search


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Farmer AI Assistant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    source_docs: list[str]
    mode: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_RETRIES = 2


def rag_only_answer(results: list[str]) -> str:
    return "\n".join(results[:3]) or "No relevant data found in database."


def call_gemini(query: str, results: list[str]) -> str:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    context = "\n".join(results)
    prompt = f"""
You are an agricultural expert.

Answer using only the context below.

Context:
{context}

Question:
{query}
"""
    client = genai.Client(api_key=api_key)
    response: Any = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=prompt,
    )
    answer = getattr(response, "text", None)
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Gemini returned an empty response")
    return answer.strip()


def generate_answer(query: str, results: list[str]) -> tuple[str, str]:
    """Try Gemini with bounded retries, then return a RAG-only answer."""
    fallback = "\n".join(results[:3]) or "No relevant data found in database."
    for attempt in range(LLM_MAX_RETRIES + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(call_gemini, query, results)
        try:
            answer = future.result(timeout=LLM_TIMEOUT_SECONDS)
            logger.info("LLM success on attempt %d", attempt + 1)
            return answer, "rag+llm"
        except FutureTimeoutError:
            logger.warning("LLM timeout on attempt %d", attempt + 1)
        except Exception:
            logger.exception("LLM failure on attempt %d", attempt + 1)
        finally:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    logger.error("LLM failed after %d attempts; using RAG-only answer", LLM_MAX_RETRIES + 1)
    return fallback, "rag"


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"success": False, "error": str(exc)})


@app.post("/ask", response_model=AskResponse | ErrorResponse)
def ask(request: AskRequest) -> AskResponse | JSONResponse:
    query = request.query.strip()
    logger.info("Incoming query: %s", query)
    try:
        results = search(query, k=10)
        logger.info("Retrieved docs count: %d", len(results))
        answer, mode = generate_answer(query, results)
        return AskResponse(answer=answer, source_docs=results[:3], mode=mode)
    except Exception as exc:
        logger.exception("Request failed")
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})