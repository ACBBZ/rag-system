from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from rag.config import get_settings
from rag.runtime import RuntimeResources, check_runtime_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    runtime: RuntimeResources | None = getattr(request.app.state, "runtime", None)
    if runtime is None:
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": {}})
    checks = await check_runtime_readiness(runtime, get_settings().minio_bucket)
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
