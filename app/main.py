from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.ingestion_jobs import router as ingestion_jobs_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.management import router as management_router
from app.api.platform import router as platform_router
from app.api.retrieval import router as retrieval_router
from rag.config import get_settings
from rag.errors import RAGError
from rag.observability import configure_tracing
from rag.runtime import close_runtime, create_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_tracing()
    app.state.runtime = create_runtime(settings)
    try:
        yield
    finally:
        await close_runtime(app.state.runtime)


app = FastAPI(title="rag-system", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(RAGError)
async def rag_error_handler(request: Request, exc: RAGError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": str(exc)},
    )


app.include_router(health_router)
app.include_router(platform_router)
app.include_router(management_router)
app.include_router(knowledge_bases_router)
app.include_router(documents_router)
app.include_router(ingestion_jobs_router)
app.include_router(retrieval_router)
