from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.management import router as management_router
from app.api.platform import router as platform_router
from app.api.retrieval import router as retrieval_router
from rag.errors import RAGError

app = FastAPI(title="rag-system")


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
app.include_router(retrieval_router)
