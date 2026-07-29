from __future__ import annotations

from hashlib import sha256

from rag.errors import NotFoundError, ValidationError
from rag.schemas import (
    EmbedDocumentResponse,
    PurgeDocumentResponse,
    TenantContext,
    UpdateDocumentResponse,
)


class IngestionPipeline:
    def __init__(
        self,
        model_client,
        object_store,
        vector_store,
        document_repository,
        *,
        max_upload_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.model_client = model_client
        self.object_store = object_store
        self.vector_store = vector_store
        self.document_repository = document_repository
        self.max_upload_bytes = max_upload_bytes

    async def embed_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        filename: str,
        content: bytes,
        title: str,
        source_uri: str | None,
        metadata: dict[str, object],
        idempotency_key: str | None = None,
    ) -> EmbedDocumentResponse:
        if not content:
            raise ValidationError("uploaded document is empty")
        if len(content) > self.max_upload_bytes:
            raise ValidationError("uploaded document exceeds configured size limit")
        if idempotency_key:
            existing = await self.document_repository.find_job_by_idempotency(
                tenant, knowledge_base_id, idempotency_key
            )
            if existing is not None and existing.document_id is not None:
                return EmbedDocumentResponse(
                    job_id=existing.job_id,
                    document_id=existing.document_id,
                    version=existing.document_version or 1,
                    status=existing.status,
                )
        safe_filename = self.object_store.safe_filename(filename)
        document_id = await self.document_repository.create_document(
            tenant,
            knowledge_base_id,
            title,
            source_uri,
        )
        version = 1
        checksum = sha256(content).hexdigest()
        raw_key = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/versions/{version}/raw/{safe_filename}"
        )
        self.object_store.put_bytes(raw_key, content, "application/octet-stream")
        try:
            job_id = await self.document_repository.create_version_and_job(
                tenant,
                knowledge_base_id,
                document_id,
                version,
                checksum=checksum,
                raw_object_key=raw_key,
                filename=safe_filename,
                metadata={**metadata, "title": title, "source_uri": source_uri},
                idempotency_key=idempotency_key,
            )
        except Exception:
            self.object_store.remove_prefix(raw_key)
            raise
        return EmbedDocumentResponse(
            job_id=job_id,
            document_id=document_id,
            version=version,
            status="queued",
        )

    async def update_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        *,
        filename: str | None = None,
        content: bytes | None = None,
        metadata: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> UpdateDocumentResponse:
        if not await self.document_repository.document_exists(
            tenant,
            knowledge_base_id,
            document_id,
        ):
            raise NotFoundError("document not found")
        version = await self.document_repository.next_version(
            tenant,
            knowledge_base_id,
            document_id,
        )
        if content is None:
            existing = await self.document_repository.get_active_version(
                tenant,
                knowledge_base_id,
                document_id,
            )
            content = self.object_store.get_bytes(existing.raw_object_key)
            filename = filename or existing.filename
            active_metadata = existing.metadata
        else:
            if not content:
                raise ValidationError("uploaded document is empty")
            if len(content) > self.max_upload_bytes:
                raise ValidationError("uploaded document exceeds configured size limit")
            active_metadata = {}
        safe_filename = self.object_store.safe_filename(filename or "upload.bin")
        checksum = sha256(content).hexdigest()
        raw_key = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/versions/{version}/raw/{safe_filename}"
        )
        self.object_store.put_bytes(raw_key, content, "application/octet-stream")
        try:
            job_id = await self.document_repository.create_version_and_job(
                tenant,
                knowledge_base_id,
                document_id,
                version,
                checksum=checksum,
                raw_object_key=raw_key,
                filename=safe_filename,
                metadata={**active_metadata, **(metadata or {})},
                idempotency_key=idempotency_key,
            )
        except Exception:
            self.object_store.remove_prefix(raw_key)
            raise
        return UpdateDocumentResponse(
            job_id=job_id,
            document_id=document_id,
            version=version,
            status="queued",
        )

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> PurgeDocumentResponse:
        if not await self.document_repository.document_exists(
            tenant,
            knowledge_base_id,
            document_id,
        ):
            raise NotFoundError("document not found")
        deactivate = getattr(self.document_repository, "deactivate_document", None)
        if callable(deactivate):
            await deactivate(tenant, knowledge_base_id, document_id)
        await self.vector_store.delete_document(tenant, knowledge_base_id, document_id)
        prefix = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/"
        )
        self.object_store.remove_prefix(prefix)
        purge = getattr(self.document_repository, "purge_document", None)
        if callable(purge):
            await purge(tenant, knowledge_base_id, document_id)
        return PurgeDocumentResponse(document_id=document_id, status="purged")
