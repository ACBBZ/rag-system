from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.retrieval.lexical import normalize_lexical_text
from rag.schemas import RetrievedChunk, TenantContext


class PostgresRetrievalStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _filter_clause(
        document_ids: list[str] | None,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        parameters: dict[str, object] = {}
        if document_ids:
            clauses.append("c.document_id = any(:document_ids)")
            parameters["document_ids"] = document_ids
        if metadata:
            clauses.append("c.metadata @> cast(:metadata_filter as jsonb)")
            parameters["metadata_filter"] = json.dumps(metadata, sort_keys=True)
        return ((" and " + " and ".join(clauses)) if clauses else "", parameters)

    async def full_text_search(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list[RetrievedChunk]:
        filter_clause, filter_parameters = self._filter_clause(document_ids, metadata)
        normalized_query = normalize_lexical_text(query)
        statement = text(
            f"""
            select c.id, c.document_id,
                   ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', :query)) as score
            from chunks c
            where c.tenant_id = :tenant_id
              and c.knowledge_base_id = :knowledge_base_id
              and c.is_active = true
              and c.search_vector @@ websearch_to_tsquery('simple', :query)
              {filter_clause}
            order by score desc, c.id asc
            limit :top_k
            """
        )
        result = await self.session.execute(
            statement,
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "query": normalized_query or query,
                "top_k": top_k,
                **filter_parameters,
            },
        )
        return [
            RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                text="",
                score=float(row["score"]),
                final_score_type="lexical",
                retrieval_method="full_text",
                retrieval_methods=["full_text"],
                scores={"full_text": float(row["score"])},
                source={},
                metadata={},
            )
            for row in result.mappings()
        ]

    async def hydrate_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        candidates: list[RetrievedChunk],
        document_ids: list[str] | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        candidate_by_id = {candidate.chunk_id: candidate for candidate in candidates}
        filter_clause, filter_parameters = self._filter_clause(document_ids, metadata)
        result = await self.session.execute(
            text(
                f"""
                select c.id, c.document_id, c.text, c.context_key,
                       coalesce(c.page_start, c.page) as page, c.metadata,
                       d.title, d.source_uri
                from chunks c
                join documents d
                  on d.id = c.document_id
                 and d.tenant_id = c.tenant_id
                 and d.knowledge_base_id = c.knowledge_base_id
                where c.tenant_id = :tenant_id
                  and c.knowledge_base_id = :knowledge_base_id
                  and c.is_active = true
                  and c.id = any(:chunk_ids)
                  {filter_clause}
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_ids": list(candidate_by_id),
                **filter_parameters,
            },
        )
        rows_by_id = {row["id"]: row for row in result.mappings()}
        hydrated: list[RetrievedChunk] = []
        for candidate in candidates:
            row = rows_by_id.get(candidate.chunk_id)
            if row is None:
                continue
            hydrated.append(
                candidate.model_copy(
                    update={
                        "document_id": row["document_id"],
                        "text": row["text"],
                        "source": {
                            "title": row["title"],
                            "source_uri": row["source_uri"],
                            "page": row["page"],
                        },
                        "metadata": {**dict(row["metadata"] or {}), "_context_key": row.get("context_key")},
                    }
                )
            )
        return hydrated

    async def log_query(
        self,
        *,
        query_id: str,
        trace_id: str,
        tenant: TenantContext,
        knowledge_base_id: str,
        query: str,
        rewritten_query: str | None,
        options: dict[str, object],
        filters: dict[str, object],
        answer_status: str,
        latency_ms: float,
        usage: dict[str, int] | None,
        model_versions: dict[str, str],
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into query_logs (
                    id, tenant_id, knowledge_base_id, query, rewritten_query, options,
                    trace_id, user_id, api_key_id, filters, answer_status,
                    total_latency_ms, prompt_tokens, completion_tokens, model_versions
                ) values (
                    :id, :tenant_id, :knowledge_base_id, :query, :rewritten_query,
                    cast(:options as jsonb), :trace_id, :user_id, :api_key_id,
                    cast(:filters as jsonb), :answer_status, :latency_ms,
                    :prompt_tokens, :completion_tokens, cast(:model_versions as jsonb)
                )
                """
            ),
            {
                "id": query_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "query": query,
                "rewritten_query": rewritten_query,
                "options": json.dumps(options),
                "trace_id": trace_id,
                "user_id": tenant.user_id,
                "api_key_id": tenant.api_key_id,
                "filters": json.dumps(filters),
                "answer_status": answer_status,
                "latency_ms": latency_ms,
                "prompt_tokens": int((usage or {}).get("prompt_tokens", 0)),
                "completion_tokens": int((usage or {}).get("completion_tokens", 0)),
                "model_versions": json.dumps(model_versions),
            },
        )

    async def log_retrievals(
        self,
        query_id: str,
        tenant: TenantContext,
        knowledge_base_id: str,
        chunks: list[RetrievedChunk],
        cited_chunk_ids: set[str],
    ) -> None:
        for rank, chunk in enumerate(chunks, start=1):
            await self.session.execute(
                text(
                    """
                    insert into retrieval_logs (
                        id, query_id, tenant_id, knowledge_base_id, chunk_id, score,
                        retrieval_method, rank, scores, selected_for_context, cited
                    ) values (
                        :id, :query_id, :tenant_id, :knowledge_base_id, :chunk_id, :score,
                        :method, :rank, cast(:scores as jsonb), true, :cited
                    )
                    """
                ),
                {
                    "id": f"ret_{query_id}_{rank}",
                    "query_id": query_id,
                    "tenant_id": tenant.tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "chunk_id": chunk.chunk_id,
                    "score": chunk.score,
                    "method": chunk.retrieval_method,
                    "rank": rank,
                    "scores": json.dumps(chunk.scores),
                    "cited": chunk.chunk_id in cited_chunk_ids,
                },
            )
