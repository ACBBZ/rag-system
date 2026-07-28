from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_retrieval_pipeline, get_tenant_context
from rag.auth import authorize_knowledge_base
from rag.retrieval.pipeline import RetrievalPipeline
from rag.schemas import RetrievalSearchRequest, RetrievalSearchResponse, TenantContext

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    request: RetrievalSearchRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[RetrievalPipeline, Depends(get_retrieval_pipeline)],
) -> RetrievalSearchResponse:
    authorize_knowledge_base(tenant, request.knowledge_base_id, required_scope="read")
    return await pipeline.search(tenant, request)
