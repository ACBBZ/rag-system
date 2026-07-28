from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    authorize_knowledge_base_access,
    get_retrieval_pipeline,
    get_session,
    get_tenant_context,
)
from rag.authz import Permission
from rag.retrieval.pipeline import RetrievalPipeline
from rag.schemas import RetrievalSearchRequest, RetrievalSearchResponse, TenantContext

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    request: RetrievalSearchRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    pipeline: Annotated[RetrievalPipeline, Depends(get_retrieval_pipeline)],
) -> RetrievalSearchResponse:
    await authorize_knowledge_base_access(
        session, tenant, request.knowledge_base_id, Permission.RETRIEVAL_READ
    )
    return await pipeline.search(tenant, request)
