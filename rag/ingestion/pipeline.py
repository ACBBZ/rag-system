from hashlib import sha256

from rag.errors import NotFoundError
from rag.ingestion.chunker import chunk_text
from rag.ingestion.cleaner import clean_text
from rag.ingestion.parsers import parse_document
from rag.models.endpoints import ModelEndpointClient
from rag.schemas import (
    EmbedDocumentResponse,
    PurgeDocumentResponse,
    TenantContext,
    UpdateDocumentResponse,
)
from rag.storage.repositories import StoredChunk


class IngestionPipeline:
    def __init__(
        self,
        model_client: ModelEndpointClient,
        object_store,
        vector_store,
        document_repository,
    ) -> None:
        self.model_client = model_client
        self.object_store = object_store
        self.vector_store = vector_store
        self.document_repository = document_repository

    async def embed_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        filename: str,
        content: bytes,
        title: str,
        source_uri: str | None,
        metadata: dict[str, object],
    ) -> EmbedDocumentResponse:
        job_id = await self.document_repository.create_job(tenant, knowledge_base_id)
        document_id = await self.document_repository.create_document_record(
            tenant,
            knowledge_base_id,
            title,
            source_uri,
        )
        checksum = sha256(content).hexdigest()
        raw_key = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/versions/1/raw/{filename}"
        )
        self.object_store.put_bytes(raw_key, content, "application/octet-stream")

        parsed = await parse_document(filename, content, self.model_client)
        cleaned_text = clean_text(parsed.text)
        parsed_key = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/versions/1/parsed/content.md"
        )
        self.object_store.put_bytes(parsed_key, cleaned_text.encode("utf-8"), "text/markdown")

        chunk_inputs = chunk_text(
            document_id,
            cleaned_text,
            {
                **metadata,
                **parsed.metadata,
                "checksum": checksum,
                "title": title,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
            },
        )
        vectors = await self.model_client.embed([chunk.text for chunk in chunk_inputs])
        chunk_ids = [f"chk_{index}_{document_id}" for index, _ in enumerate(chunk_inputs, start=1)]
        await self.document_repository.store_chunks(
            [
                StoredChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
                for chunk_id, chunk in zip(chunk_ids, chunk_inputs, strict=True)
            ]
        )
        await self.vector_store.upsert_chunks(
            tenant,
            knowledge_base_id,
            document_id,
            chunk_ids,
            vectors,
        )
        return EmbedDocumentResponse(job_id=job_id, document_id=document_id, status="queued")

    async def update_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> UpdateDocumentResponse:
        if not await self.document_repository.document_exists(
            tenant, knowledge_base_id, document_id
        ):
            raise NotFoundError("document not found")
        job_id = await self.document_repository.create_job(tenant, knowledge_base_id)
        return UpdateDocumentResponse(
            job_id=job_id,
            document_id=document_id,
            version=2,
            status="queued",
        )

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> PurgeDocumentResponse:
        if not await self.document_repository.document_exists(
            tenant, knowledge_base_id, document_id
        ):
            raise NotFoundError("document not found")
        await self.vector_store.delete_document(tenant, knowledge_base_id, document_id)
        prefix = (
            f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/"
            f"{document_id}/"
        )
        self.object_store.remove_prefix(prefix)
        await self.document_repository.purge_document(tenant, knowledge_base_id, document_id)
        return PurgeDocumentResponse(document_id=document_id, status="purged")
