from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.schemas import RetrievedChunk, TenantContext


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class StoredChunk:
    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, object]


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        key_hash = api_key
        result = await self.session.execute(
            text(
                """
                select tenant_id, organization_id, user_id, allowed_scopes, knowledge_base_ids
                from api_keys
                where key_hash = :key_hash and is_active = true
                """
            ),
            {"key_hash": key_hash},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return TenantContext(
            tenant_id=row["tenant_id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            knowledge_base_ids=list(row["knowledge_base_ids"]),
            roles=[],
            allowed_scopes=list(row["allowed_scopes"]),
        )


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, tenant: TenantContext, knowledge_base_id: str) -> str:
        job_id = new_id("job")
        await self.session.execute(
            text(
                """
                insert into ingestion_jobs (id, tenant_id, knowledge_base_id, status)
                values (:id, :tenant_id, :knowledge_base_id, 'queued')
                """
            ),
            {"id": job_id, "tenant_id": tenant.tenant_id, "knowledge_base_id": knowledge_base_id},
        )
        return job_id

    async def create_document_record(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        title: str,
        source_uri: str | None,
    ) -> str:
        document_id = new_id("doc")
        await self.session.execute(
            text(
                """
                insert into documents (id, tenant_id, knowledge_base_id, title, source_uri)
                values (:id, :tenant_id, :knowledge_base_id, :title, :source_uri)
                """
            ),
            {
                "id": document_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "title": title,
                "source_uri": source_uri,
            },
        )
        return document_id

    async def store_chunks(self, chunks: list[StoredChunk]) -> None:
        for chunk in chunks:
            await self.session.execute(
                text(
                    """
                    insert into chunks (
                        id, tenant_id, knowledge_base_id, document_id, document_version,
                        text, token_count, metadata
                    )
                    values (
                        :id, :tenant_id, :knowledge_base_id, :document_id, 1,
                        :text, :token_count, :metadata
                    )
                    """
                ),
                {
                    "id": chunk.chunk_id,
                    "tenant_id": chunk.metadata["tenant_id"],
                    "knowledge_base_id": chunk.metadata["knowledge_base_id"],
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "token_count": len(chunk.text.split()),
                    "metadata": chunk.metadata,
                },
            )

    async def hydrate_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        candidate_by_id = {candidate.chunk_id: candidate for candidate in candidates}
        result = await self.session.execute(
            text(
                """
                select c.id, c.document_id, c.text, c.page, c.metadata, d.title, d.source_uri
                from chunks c
                join documents d on d.id = c.document_id
                where c.tenant_id = :tenant_id
                  and c.knowledge_base_id = :knowledge_base_id
                  and c.is_active = true
                  and c.id = any(:chunk_ids)
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_ids": list(candidate_by_id),
            },
        )
        hydrated = []
        for row in result.mappings():
            candidate = candidate_by_id[row["id"]]
            hydrated.append(
                candidate.model_copy(
                    update={
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

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into deletion_audit_events (
                    id, tenant_id, knowledge_base_id, document_id, actor_user_id, event_type
                )
                values (:id, :tenant_id, :knowledge_base_id, :document_id, :actor_user_id, 'purge')
                """
            ),
            {
                "id": new_id("del"),
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "actor_user_id": tenant.user_id,
            },
        )
        await self.session.execute(
            text(
                """
                delete from keyword_postings
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and chunk_id in (
                    select id from chunks
                    where tenant_id = :tenant_id
                      and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                  )
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        for table_name in ["chunks", "document_versions"]:
            await self.session.execute(
                text(
                    f"""
                    delete from {table_name}
                    where tenant_id = :tenant_id
                      and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                    """
                ),
                {
                    "tenant_id": tenant.tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                },
            )
        await self.session.execute(
            text(
                """
                delete from documents
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and id = :document_id
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
