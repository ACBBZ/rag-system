import asyncio
from uuid import uuid4

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.context import build_context
from rag.retrieval.fusion import rrf_fusion
from rag.retrieval.options import resolve_retrieval_options
from rag.schemas import (
    Citation,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetrievedChunk,
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

    async def _vector_search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        vectors = await self.model_client.embed([query])
        candidate_k = min(top_k * 5, 500) if request.filters.metadata else top_k
        return await self.vector_store.search(
            tenant,
            request.knowledge_base_id,
            vectors[0],
            candidate_k,
            document_ids=request.filters.document_ids or None,
        )

    async def _full_text_search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return await self.document_repository.full_text_search(
            tenant,
            request.knowledge_base_id,
            query,
            top_k,
            document_ids=request.filters.document_ids or None,
            metadata=request.filters.metadata or None,
        )

    async def search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
    ) -> RetrievalSearchResponse:
        query_id = f"qry_{uuid4().hex}"
        effective = resolve_retrieval_options(self.settings, request.options)
        query = request.query
        rewritten_query = None

        if effective.query_rewrite:
            rewritten_query = await self.model_client.rewrite(query)
            query = rewritten_query

        if effective.hybrid_search:
            vector_results, full_text_results = await asyncio.gather(
                self._vector_search(tenant, request, query, effective.top_k),
                self._full_text_search(tenant, request, query, effective.top_k),
            )
            chunks = rrf_fusion(
                [vector_results, full_text_results],
                weights=[1.0, 0.8],
            )
        elif effective.vector_search:
            chunks = await self._vector_search(tenant, request, query, effective.top_k)
        else:
            chunks = await self._full_text_search(tenant, request, query, effective.top_k)

        chunks = await self.document_repository.hydrate_chunks(
            tenant,
            request.knowledge_base_id,
            chunks,
            document_ids=request.filters.document_ids or None,
            metadata=request.filters.metadata or None,
        )

        if effective.rerank and chunks:
            scores = await self.model_client.rerank(query, [chunk.text for chunk in chunks])
            reranked: list[RetrievedChunk] = []
            for chunk, score in zip(chunks, scores, strict=True):
                methods = list(dict.fromkeys([*chunk.retrieval_methods, "rerank"]))
                reranked.append(
                    chunk.model_copy(
                        update={
                            "score": score,
                            "retrieval_method": f"{chunk.retrieval_method}_rerank",
                            "retrieval_methods": methods,
                            "scores": {**chunk.scores, "rerank": score},
                        }
                    )
                )
            chunks = sorted(reranked, key=lambda chunk: chunk.score, reverse=True)

        final_chunks = chunks[: effective.final_k]
        answer = None
        citations: list[Citation] = []
        usage = None

        if effective.agent_search:
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
            effective_options=effective.model_dump(),
            chunks=final_chunks,
            answer=answer,
            citations=citations,
            usage=usage,
        )
