from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.ingestion.chunker import ChunkInput
from rag.ingestion.jobs import ClaimedIngestionJob
from rag.schemas import IngestionJobResponse, TenantContext, TenantVectorRoute


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class ExistingVersion:
    raw_object_key: str
    filename: str
    checksum: str
    metadata: dict[str, object]


class IngestionRepository:
    def __init__(self, session: AsyncSession, *, max_attempts: int = 3) -> None:
        self.session = session
        self.max_attempts = max_attempts

    @staticmethod
    def _job_response(row) -> IngestionJobResponse:
        return IngestionJobResponse(
            job_id=row["id"],
            document_id=row["document_id"],
            document_version=row["document_version"],
            status=row["status"],
            stage=row["stage"],
            progress=float(row["progress"] or 0),
            attempt=int(row["attempt"] or 0),
            max_attempts=int(row["max_attempts"] or 0),
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def find_job_by_idempotency(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> IngestionJobResponse | None:
        result = await self.session.execute(
            text(
                """
                select * from ingestion_jobs
                where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                  and idempotency_key = :idempotency_key
                limit 1
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "idempotency_key": idempotency_key,
            },
        )
        row = result.mappings().first()
        return self._job_response(row) if row is not None else None

    async def create_document(
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
                insert into documents (
                    id, tenant_id, knowledge_base_id, title, source_uri,
                    active_version, is_active
                ) values (
                    :id, :tenant_id, :knowledge_base_id, :title, :source_uri, 0, true
                )
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

    async def document_exists(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool:
        result = await self.session.execute(
            text(
                """
                select 1 from documents
                where id = :document_id and tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id and is_active = true
                """
            ),
            {
                "document_id": document_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
            },
        )
        return result.first() is not None

    async def next_version(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> int:
        result = await self.session.execute(
            text(
                """
                select coalesce(max(version), 0) + 1
                from document_versions
                where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        return int(result.scalar_one())

    async def create_version_and_job(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        version: int,
        *,
        checksum: str,
        raw_object_key: str,
        filename: str,
        metadata: dict[str, object],
        idempotency_key: str | None,
    ) -> str:
        version_id = new_id("ver")
        job_id = new_id("job")
        payload = json.dumps(metadata, ensure_ascii=False)
        await self.session.execute(
            text(
                """
                insert into document_versions (
                    id, tenant_id, knowledge_base_id, document_id, version,
                    checksum, raw_object_key, parsed_object_key, metadata,
                    status, filename
                ) values (
                    :id, :tenant_id, :knowledge_base_id, :document_id, :version,
                    :checksum, :raw_object_key, null, cast(:metadata as jsonb),
                    'staging', :filename
                )
                """
            ),
            {
                "id": version_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "version": version,
                "checksum": checksum,
                "raw_object_key": raw_object_key,
                "metadata": payload,
                "filename": filename,
            },
        )
        await self.session.execute(
            text(
                """
                insert into ingestion_jobs (
                    id, tenant_id, knowledge_base_id, document_id,
                    document_version, status, stage, progress, attempt,
                    max_attempts, available_at, idempotency_key,
                    raw_object_key, filename, metadata
                ) values (
                    :id, :tenant_id, :knowledge_base_id, :document_id,
                    :document_version, 'queued', 'queued', 0, 0,
                    :max_attempts, now(), :idempotency_key,
                    :raw_object_key, :filename, cast(:metadata as jsonb)
                )
                """
            ),
            {
                "id": job_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "document_version": version,
                "max_attempts": self.max_attempts,
                "idempotency_key": idempotency_key,
                "raw_object_key": raw_object_key,
                "filename": filename,
                "metadata": payload,
            },
        )
        return job_id

    async def get_active_version(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> ExistingVersion:
        result = await self.session.execute(
            text(
                """
                select v.raw_object_key, v.filename, v.checksum, v.metadata
                from documents d
                join document_versions v
                  on v.tenant_id = d.tenant_id
                 and v.knowledge_base_id = d.knowledge_base_id
                 and v.document_id = d.id
                 and v.version = d.active_version
                where d.tenant_id = :tenant_id
                  and d.knowledge_base_id = :knowledge_base_id
                  and d.id = :document_id and d.is_active = true
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        row = result.mappings().one()
        return ExistingVersion(
            raw_object_key=row["raw_object_key"],
            filename=row["filename"],
            checksum=row["checksum"],
            metadata=dict(row["metadata"] or {}),
        )

    async def claim_next_job(self, worker_id: str) -> ClaimedIngestionJob | None:
        result = await self.session.execute(
            text(
                """
                with candidate as (
                    select id from ingestion_jobs
                    where status in ('queued', 'failed_retryable')
                      and available_at <= now() and attempt < max_attempts
                    order by created_at
                    for update skip locked
                    limit 1
                )
                update ingestion_jobs j
                set status = 'parsing', stage = 'parsing', progress = 0.05,
                    attempt = attempt + 1, worker_id = :worker_id,
                    started_at = coalesce(started_at, now()),
                    heartbeat_at = now(), updated_at = now()
                from candidate
                where j.id = candidate.id
                returning j.*
                """
            ),
            {"worker_id": worker_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        route_result = await self.session.execute(
            text(
                """
                select logical_alias, physical_collection, schema_version,
                       embedding_model, embedding_dimension, metric_type,
                       index_type, search_params
                from tenant_vector_resources
                where tenant_id = :tenant_id and status = 'ready'
                limit 1
                """
            ),
            {"tenant_id": row["tenant_id"]},
        )
        route_row = route_result.mappings().first()
        route = None
        if route_row is not None:
            route = TenantVectorRoute(
                collection_alias=route_row["logical_alias"],
                physical_collection=route_row["physical_collection"],
                schema_version=int(route_row["schema_version"]),
                embedding_model=route_row["embedding_model"],
                embedding_dimension=int(route_row["embedding_dimension"]),
                metric_type=route_row["metric_type"],
                index_type=route_row["index_type"],
                search_params=dict(route_row["search_params"] or {}),
            )
        tenant_context = TenantContext(
            tenant_id=row["tenant_id"],
            user_id="system",
            vector_route=route,
        )
        return ClaimedIngestionJob(
            job_id=row["id"],
            tenant_id=row["tenant_id"],
            knowledge_base_id=row["knowledge_base_id"],
            document_id=row["document_id"],
            document_version=int(row["document_version"]),
            raw_object_key=row["raw_object_key"],
            filename=row["filename"],
            metadata=dict(row["metadata"] or {}),
            tenant_context=tenant_context,
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def set_job_stage(
        self,
        job_id: str,
        stage: str,
        *,
        progress: float | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        terminal = stage in {"completed", "failed_terminal", "cancelled"}
        await self.session.execute(
            text(
                """
                update ingestion_jobs
                set status = :stage, stage = :stage,
                    progress = coalesce(:progress, progress),
                    heartbeat_at = now(), error_code = :error_code,
                    error_message = :error_message,
                    completed_at = case when :terminal then now() else completed_at end,
                    updated_at = now()
                where id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "stage": stage,
                "progress": progress,
                "error_code": error_code,
                "error_message": error_message,
                "terminal": terminal,
            },
        )

    async def replace_staging_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        version: int,
        chunks: list[ChunkInput],
        parsed_object_key: str,
    ) -> None:
        params = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "version": version,
        }
        await self.session.execute(
            text(
                """
                delete from chunks
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id
                  and document_version = :version
                """
            ),
            params,
        )
        statement = text(
            """
            insert into chunks (
                id, tenant_id, knowledge_base_id, document_id,
                document_version, ordinal, text, title_path, page,
                page_start, page_end, token_count, metadata, is_active,
                content_hash, context_key, parent_chunk_id, language,
                parser_version, chunker_version, lexical_text
            ) values (
                :id, :tenant_id, :knowledge_base_id, :document_id,
                :version, :ordinal, :text, cast(:title_path as jsonb),
                :page, :page_start, :page_end, :token_count,
                cast(:metadata as jsonb), false, :content_hash,
                :context_key, :parent_chunk_id, :language,
                'structured-v2', 'token-v2', :lexical_text
            )
            """
        )
        for chunk in chunks:
            await self.session.execute(
                statement,
                {
                    **params,
                    "id": chunk.chunk_id,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "title_path": json.dumps(chunk.title_path),
                    "page": chunk.page,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "token_count": chunk.token_count,
                    "metadata": json.dumps(chunk.metadata, ensure_ascii=False),
                    "content_hash": chunk.content_hash,
                    "context_key": chunk.context_key,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "language": chunk.language,
                    "lexical_text": chunk.text,
                },
            )
        await self.session.execute(
            text(
                """
                update document_versions
                set parsed_object_key = :parsed_object_key, updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id and version = :version
                """
            ),
            {**params, "parsed_object_key": parsed_object_key},
        )

    async def activate_document_version(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        version: int,
    ) -> None:
        params = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "version": version,
        }
        await self.session.execute(
            text(
                """
                update chunks
                set is_active = (document_version = :version), updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id
                """
            ),
            params,
        )
        await self.session.execute(
            text(
                """
                update document_versions
                set status = case
                    when version = :version then 'active' else 'superseded'
                end, updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id
                """
            ),
            params,
        )
        await self.session.execute(
            text(
                """
                update documents
                set active_version = :version, updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and id = :document_id
                """
            ),
            params,
        )

    async def get_job(
        self,
        tenant: TenantContext,
        job_id: str,
    ) -> IngestionJobResponse | None:
        result = await self.session.execute(
            text(
                """
                select * from ingestion_jobs
                where id = :job_id and tenant_id = :tenant_id
                """
            ),
            {"job_id": job_id, "tenant_id": tenant.tenant_id},
        )
        row = result.mappings().first()
        return self._job_response(row) if row is not None else None

    async def retry_job(self, tenant: TenantContext, job_id: str) -> bool:
        result = await self.session.execute(
            text(
                """
                update ingestion_jobs
                set status = 'queued', stage = 'queued', available_at = now(),
                    error_code = null, error_message = null, updated_at = now()
                where id = :job_id and tenant_id = :tenant_id
                  and status in ('failed_retryable', 'failed_terminal')
                  and attempt < max_attempts
                """
            ),
            {"job_id": job_id, "tenant_id": tenant.tenant_id},
        )
        return bool(result.rowcount)

    async def deactivate_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        params = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
        }
        await self.session.execute(
            text(
                """
                update documents set is_active = false, updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and id = :document_id
                """
            ),
            params,
        )
        await self.session.execute(
            text(
                """
                update chunks set is_active = false, updated_at = now()
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and document_id = :document_id
                """
            ),
            params,
        )

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        params = {
            "tenant_id": tenant.tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
        }
        for table in ("ingestion_jobs", "chunks", "document_versions"):
            await self.session.execute(
                text(
                    f"""
                    delete from {table}
                    where tenant_id = :tenant_id
                      and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                    """
                ),
                params,
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
            params,
        )
