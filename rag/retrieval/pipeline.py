from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from uuid import uuid4

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient
from rag.observability import ABSTENTION_TOTAL, QUERY_LATENCY, QUERY_TOTAL, timed_span
from rag.retrieval.citations import CitationValidationError, validate_citations
from rag.retrieval.context import ContextBudget, build_context
from rag.retrieval.fusion import rrf_fusion
from rag.retrieval.generation import normalize_generated_answer
from rag.retrieval.options import resolve_retrieval_options
from rag.schemas import (
    GeneratedAnswer,
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
        try:
            return await self.vector_store.search(
                tenant,
                request.knowledge_base_id,
                vectors[0],
                top_k,
                document_ids=request.filters.document_ids or None,
                metadata=request.filters.metadata or None,
            )
        except TypeError:
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

    @staticmethod
    def _limit_per_document(
        chunks: list[RetrievedChunk],
        limit: int,
    ) -> list[RetrievedChunk]:
        counts: dict[str, int] = defaultdict(int)
        result: list[RetrievedChunk] = []
        seen_text: set[str] = set()
        for chunk in chunks:
            fingerprint = chunk.text.strip().casefold()
            if fingerprint and fingerprint in seen_text:
                continue
            if counts[chunk.document_id] >= limit:
                continue
            counts[chunk.document_id] += 1
            if fingerprint:
                seen_text.add(fingerprint)
            result.append(chunk)
        return result

    async def search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
    ) -> RetrievalSearchResponse:
        started = time.perf_counter()
        query_id = f"qry_{uuid4().hex}"
        trace_id = f"trace_{uuid4().hex}"
        timings: dict[str, float] = {}
        effective = resolve_retrieval_options(self.settings, request.options)
        query = request.query
        rewritten_query = None
        degraded_components: list[str] = []

        if effective.query_rewrite:
            with timed_span("rag.query_rewrite", trace_id=trace_id) as timing:
                try:
                    rewritten_query = await self.model_client.rewrite(query)
                    query = rewritten_query
                except Exception:
                    if not effective.allow_partial_results:
                        raise
                    degraded_components.append("query_rewrite")
            timings["rewrite_ms"] = timing["milliseconds"]

        with timed_span(
            "rag.retrieval",
            mode=effective.retrieval_mode,
            trace_id=trace_id,
        ) as timing:
            if effective.hybrid_search:
                vector_results, full_text_results = await asyncio.gather(
                    self._vector_search(tenant, request, query, effective.top_k),
                    self._full_text_search(tenant, request, query, effective.top_k),
                )
                chunks = rrf_fusion(
                    [vector_results, full_text_results],
                    k=effective.rrf_k,
                    weights=[effective.vector_weight, effective.lexical_weight],
                )
            elif effective.vector_search:
                chunks = await self._vector_search(
                    tenant,
                    request,
                    query,
                    effective.top_k,
                )
            else:
                chunks = await self._full_text_search(
                    tenant,
                    request,
                    query,
                    effective.top_k,
                )
        timings["retrieval_ms"] = timing["milliseconds"]

        chunks = await self.document_repository.hydrate_chunks(
            tenant,
            request.knowledge_base_id,
            chunks,
            document_ids=request.filters.document_ids or None,
            metadata=request.filters.metadata or None,
        )
        if effective.score_threshold is not None:
            chunks = [
                chunk for chunk in chunks if chunk.score >= effective.score_threshold
            ]
        chunks = self._limit_per_document(chunks, effective.per_document_limit)

        if effective.rerank and chunks:
            rerank_pool = chunks[: effective.rerank_candidate_k]
            with timed_span("rag.rerank", trace_id=trace_id) as timing:
                scores = await self.model_client.rerank(
                    query,
                    [chunk.text for chunk in rerank_pool],
                )
            timings["rerank_ms"] = timing["milliseconds"]
            reranked: list[RetrievedChunk] = []
            for chunk, score in zip(rerank_pool, scores, strict=True):
                methods = list(dict.fromkeys([*chunk.retrieval_methods, "rerank"]))
                reranked.append(
                    chunk.model_copy(
                        update={
                            "score": score,
                            "final_score_type": "rerank",
                            "retrieval_method": f"{chunk.retrieval_method}_rerank",
                            "retrieval_methods": methods,
                            "scores": {**chunk.scores, "rerank": score},
                        }
                    )
                )
            chunks = sorted(reranked, key=lambda item: item.score, reverse=True)

        final_chunks = chunks[: effective.final_k]
        answer = None
        answer_status = "not_requested"
        abstention_reason = None
        citations = []
        usage = None
        generated = GeneratedAnswer(
            answer=None,
            abstained=True,
            abstention_reason="not_requested",
        )

        if effective.agent_search:
            if not final_chunks:
                answer_status = "insufficient_context"
                abstention_reason = "no_retrieval_results"
                ABSTENTION_TOTAL.labels(reason=abstention_reason).inc()
            else:
                context = build_context(
                    final_chunks,
                    budget=ContextBudget(
                        max_context_tokens=getattr(
                            self.settings,
                            "context_max_tokens",
                            6000,
                        )
                    ),
                )
                with timed_span("rag.generation", trace_id=trace_id) as timing:
                    generated_value, raw_usage = await self.model_client.answer(
                        request.query,
                        context,
                    )
                timings["generation_ms"] = timing["milliseconds"]
                generated = normalize_generated_answer(generated_value)
                usage = Usage(**raw_usage)
                if generated.abstained:
                    answer_status = "insufficient_context"
                    abstention_reason = generated.abstention_reason or "model_abstained"
                    ABSTENTION_TOTAL.labels(reason=abstention_reason).inc()
                else:
                    try:
                        citations = validate_citations(generated, final_chunks)
                    except CitationValidationError:
                        answer_status = "generation_failed"
                        raise
                    answer = generated.answer
                    answer_status = "answered"

        total_ms = (time.perf_counter() - started) * 1000
        timings["total_ms"] = total_ms
        QUERY_TOTAL.labels(
            mode=effective.retrieval_mode,
            status=answer_status,
        ).inc()
        QUERY_LATENCY.labels(mode=effective.retrieval_mode).observe(total_ms / 1000)

        log_query = getattr(self.document_repository, "log_query", None)
        if callable(log_query):
            await log_query(
                query_id=query_id,
                trace_id=trace_id,
                tenant=tenant,
                knowledge_base_id=request.knowledge_base_id,
                query=request.query,
                rewritten_query=rewritten_query,
                options=effective.model_dump(),
                filters=request.filters.model_dump(),
                answer_status=answer_status,
                latency_ms=total_ms,
                usage=usage.model_dump() if usage else None,
                model_versions={
                    "embedding": self.settings.embedding_model,
                    "rerank": self.settings.rerank_model,
                    "generator": self.settings.llm_model,
                },
            )
        log_retrievals = getattr(self.document_repository, "log_retrievals", None)
        if callable(log_retrievals):
            await log_retrievals(
                query_id,
                tenant,
                request.knowledge_base_id,
                final_chunks,
                set(generated.cited_chunk_ids),
            )

        return RetrievalSearchResponse(
            query_id=query_id,
            trace_id=trace_id,
            rewritten_query=rewritten_query,
            effective_options=effective.model_dump(),
            chunks=final_chunks,
            answer=answer,
            answer_status=answer_status,
            abstention_reason=abstention_reason,
            citations=citations,
            usage=usage,
            timings=(
                timings
                if effective.include_diagnostics
                else {"total_ms": total_ms}
            ),
            degraded=bool(degraded_components),
            degraded_components=degraded_components,
        )
