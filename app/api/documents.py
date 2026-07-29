from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from app.api.dependencies import (
    authorize_knowledge_base_access,
    get_ingestion_pipeline,
    get_tenant_context,
)
from rag.authz import Permission
from rag.errors import ValidationError
from rag.ingestion.pipeline import IngestionPipeline
from rag.schemas import (
    EmbedDocumentResponse,
    PurgeDocumentResponse,
    TenantContext,
    UpdateDocumentResponse,
)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise ValidationError("uploaded document exceeds configured size limit")
    return content


@router.post("/embed", response_model=EmbedDocumentResponse, status_code=202)
async def embed_document(
    knowledge_base_id: Annotated[str, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
    source_uri: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> EmbedDocumentResponse:
    authorize_knowledge_base_access(tenant, knowledge_base_id, Permission.DOCUMENTS_CREATE)
    content = await _read_limited(file, pipeline.max_upload_bytes)
    return await pipeline.embed_document(
        tenant=tenant,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or "upload.bin",
        content=content,
        title=title,
        source_uri=source_uri,
        metadata={"content_type": file.content_type or "application/octet-stream"},
        idempotency_key=idempotency_key,
    )


@router.patch("/{document_id}", response_model=UpdateDocumentResponse, status_code=202)
async def update_document(
    document_id: str,
    knowledge_base_id: Annotated[str, Form()],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
    file: Annotated[UploadFile | None, File()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> UpdateDocumentResponse:
    authorize_knowledge_base_access(tenant, knowledge_base_id, Permission.DOCUMENTS_UPDATE)
    content = await _read_limited(file, pipeline.max_upload_bytes) if file else None
    return await pipeline.update_document(
        tenant,
        knowledge_base_id,
        document_id,
        filename=file.filename if file else None,
        content=content,
        metadata={"content_type": file.content_type} if file else {},
        idempotency_key=idempotency_key,
    )


@router.delete("/{document_id}/purge", response_model=PurgeDocumentResponse)
async def purge_document(
    document_id: str,
    knowledge_base_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> PurgeDocumentResponse:
    authorize_knowledge_base_access(tenant, knowledge_base_id, Permission.DOCUMENTS_DELETE)
    return await pipeline.purge_document(tenant, knowledge_base_id, document_id)
