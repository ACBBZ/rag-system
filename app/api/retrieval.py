from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_api_key
from rag.schemas import RetrievalSearchRequest, RetrievalSearchResponse

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    request: RetrievalSearchRequest,
    api_key: Annotated[str, Depends(get_api_key)],
) -> RetrievalSearchResponse:
    return RetrievalSearchResponse(
        query_id="qry_test",
        rewritten_query=None,
        chunks=[],
        answer=None,
        citations=[],
        usage=None,
    )
