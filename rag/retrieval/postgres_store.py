import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
        if not clauses:
            return "", parameters
        return " and " + " and ".join(clauses), parameters

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
        statement = text(
            f"""
            select c.id, c.document_id,
                   ts_rank_cd(
                       c.search_vector,
                       websearch_to_tsquery('simple', :query)
                   ) as score
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
        parameters = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "query": query,
            "top_k": top_k,
            **filter_parameters,
        }
        result = await self.session.execute(statement, parameters)
        return [
            RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                text="",
                score=float(row["score"]),
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
        statement = text(
            f"""
            select c.id, c.document_id, c.text, c.page, c.metadata,
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
        )
        parameters = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "chunk_ids": list(candidate_by_id),
            **filter_parameters,
        }
        result = await self.session.execute(statement, parameters)
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
                        "metadata": row["metadata"],
                    }
                )
            )
        return hydrated
