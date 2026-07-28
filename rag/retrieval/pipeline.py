from uuid import uuid4

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.context import build_context
from rag.retrieval.fusion import rrf_fusion
from rag.schemas import (
    Citation,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    TenantContext,
    Usage,
)


class RetrievalPipeline:
    def __init__(
        self,
        settings: Settings,
        model_client: ModelEndpointClient,
        document_repository,
        vector_store,
    ) -> None:
        self.settings = settings
        self.model_client = model_client
        self.document_repository = document_repository
        self.vector_store = vector_store

    async def search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
    ) -> RetrievalSearchResponse:
        query_id = f"qry_{uuid4().hex}"
        query = request.query
        rewritten_query = None

        if request.options.query_rewrite:
            rewritten_query = await self.model_client.rewrite(query)
            query = rewritten_query

        candidates = []
        if request.options.vector_search is not False:
            vectors = await self.model_client.embed([query])
            candidates.append(
                self.vector_store.search(
                    tenant,
                    request.knowledge_base_id,
                    vectors[0],
                    request.options.top_k,
                )
            )

        chunks = rrf_fusion(candidates) if len(candidates) > 1 else candidates[0] if candidates else []
        chunks = await self.document_repository.hydrate_chunks(
            tenant,
            request.knowledge_base_id,
            chunks,
        )

        if request.options.rerank and chunks:
            scores = await self.model_client.rerank(query, [chunk.text for chunk in chunks])
            chunks = [
                chunk.model_copy(
                    update={
                        "score": score,
                        "retrieval_method": f"{chunk.retrieval_method}_rerank",
                    }
                )
                for chunk, score in zip(chunks, scores, strict=True)
            ]
            chunks.sort(key=lambda chunk: chunk.score, reverse=True)

        final_chunks = chunks[: request.options.final_k]
        answer = None
        citations: list[Citation] = []
        usage = None

        if request.options.agent_search:
            context = build_context(final_chunks)
            answer, raw_usage = await self.model_client.answer(request.query, context)
            usage = Usage(**raw_usage)
            citations = [
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=str(chunk.source.get("title")) if chunk.source.get("title") else None,
                    source_uri=(
                        str(chunk.source.get("source_uri"))
                        if chunk.source.get("source_uri")
                        else None
                    ),
                    page=int(chunk.source["page"]) if chunk.source.get("page") is not None else None,
                    quote=chunk.text[:240],
                )
                for chunk in final_chunks
            ]

        return RetrievalSearchResponse(
            query_id=query_id,
            rewritten_query=rewritten_query,
            chunks=final_chunks,
            answer=answer,
            citations=citations,
            usage=usage,
        )
