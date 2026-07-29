from __future__ import annotations

import traceback

from rag.ingestion.chunker import ChunkingConfig, chunk_document
from rag.ingestion.cleaner import clean_text
from rag.ingestion.parsers import parse_document
from rag.observability import INGESTION_JOBS
from rag.schemas import TenantContext


class IngestionWorker:
    def __init__(
        self,
        *,
        repository,
        object_store,
        model_client,
        vector_store,
        worker_id: str,
        chunking_config: ChunkingConfig | None = None,
        parser_limits: dict[str, int] | None = None,
    ) -> None:
        self.repository = repository
        self.object_store = object_store
        self.model_client = model_client
        self.vector_store = vector_store
        self.worker_id = worker_id
        self.chunking_config = chunking_config or ChunkingConfig()
        self.parser_limits = parser_limits or {}

    async def _checkpoint(self) -> None:
        checkpoint = getattr(self.repository, "checkpoint", None)
        if callable(checkpoint):
            await checkpoint()
            return
        session = getattr(self.repository, "session", None)
        commit = getattr(session, "commit", None)
        if callable(commit):
            await commit()

    async def run_once(self) -> bool:
        job = await self.repository.claim_next_job(self.worker_id)
        if job is None:
            return False
        await self._checkpoint()
        tenant = getattr(job, "tenant_context", None) or TenantContext(
            tenant_id=job.tenant_id,
            user_id="system",
        )
        try:
            content = self.object_store.get_bytes(job.raw_object_key)
            await self.repository.set_job_stage(job.job_id, "parsing", progress=0.1)
            parsed = await parse_document(
                job.filename,
                content,
                self.model_client,
                **self.parser_limits,
            )
            await self.repository.set_job_stage(job.job_id, "chunking", progress=0.25)
            chunks = chunk_document(
                job.document_id,
                job.document_version,
                parsed,
                {
                    **job.metadata,
                    "tenant_id": job.tenant_id,
                    "knowledge_base_id": job.knowledge_base_id,
                },
                config=self.chunking_config,
            )
            if not chunks:
                raise ValueError("document produced no chunks")
            await self.repository.set_job_stage(job.job_id, "embedding", progress=0.45)
            vectors = await self.model_client.embed([chunk.text for chunk in chunks])
            parsed_key = (
                f"tenants/{job.tenant_id}/knowledge_bases/{job.knowledge_base_id}/documents/"
                f"{job.document_id}/versions/{job.document_version}/parsed/content.md"
            )
            self.object_store.put_bytes(parsed_key, clean_text(parsed.text).encode("utf-8"), "text/markdown")
            await self.repository.replace_staging_chunks(
                tenant,
                job.knowledge_base_id,
                job.document_id,
                job.document_version,
                chunks,
                parsed_key,
            )
            await self.repository.set_job_stage(job.job_id, "indexing", progress=0.7)
            try:
                await self.vector_store.upsert_chunks(
                    tenant,
                    job.knowledge_base_id,
                    job.document_id,
                    [chunk.chunk_id for chunk in chunks],
                    vectors,
                    document_version=job.document_version,
                    metadata=[chunk.metadata for chunk in chunks],
                    languages=[chunk.language for chunk in chunks],
                    pages=[chunk.page_start for chunk in chunks],
                    is_active=False,
                )
            except TypeError:
                await self.vector_store.upsert_chunks(
                    tenant,
                    job.knowledge_base_id,
                    job.document_id,
                    [chunk.chunk_id for chunk in chunks],
                    vectors,
                )
            await self.repository.set_job_stage(job.job_id, "validating", progress=0.85)
            if len(vectors) != len(chunks):
                raise ValueError("vector count does not match chunk count")
            await self.repository.set_job_stage(job.job_id, "activating", progress=0.95)
            try:
                await self.vector_store.upsert_chunks(
                    tenant,
                    job.knowledge_base_id,
                    job.document_id,
                    [chunk.chunk_id for chunk in chunks],
                    vectors,
                    document_version=job.document_version,
                    metadata=[chunk.metadata for chunk in chunks],
                    languages=[chunk.language for chunk in chunks],
                    pages=[chunk.page_start for chunk in chunks],
                    is_active=True,
                )
            except TypeError:
                pass
            await self.repository.activate_document_version(
                tenant,
                job.knowledge_base_id,
                job.document_id,
                job.document_version,
            )
            activate = getattr(self.vector_store, "activate_document_version", None)
            if callable(activate):
                await activate(tenant, job.knowledge_base_id, job.document_id, job.document_version)
            await self.repository.set_job_stage(job.job_id, "completed", progress=1.0)
            await self._checkpoint()
            INGESTION_JOBS.labels(status="completed").inc()
            return True
        except Exception as exc:
            status = "failed_retryable" if job.attempt < job.max_attempts else "failed_terminal"
            await self.repository.set_job_stage(
                job.job_id,
                status,
                error_code=type(exc).__name__,
                error_message=f"{exc}\n{traceback.format_exc(limit=5)}"[:4000],
            )
            await self._checkpoint()
            INGESTION_JOBS.labels(status=status).inc()
            return True
