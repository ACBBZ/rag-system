from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_ingestion_pipeline, get_tenant_context
from rag.ingestion.pipeline import IngestionPipeline
from rag.schemas import (
    EmbedDocumentResponse,
    PurgeDocumentResponse,
    TenantContext,
    UpdateDocumentResponse,
)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/embed", response_model=EmbedDocumentResponse)
async def embed_document(
    knowledge_base_id: Annotated[str, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
    source_uri: Annotated[str | None, Form()] = None,
) -> EmbedDocumentResponse:
    content = await file.read()
    return await pipeline.embed_document(
        tenant=tenant,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or "upload.bin",
        content=content,
        title=title,
        source_uri=source_uri,
        metadata={},
    )


@router.patch("/{document_id}", response_model=UpdateDocumentResponse)
async def update_document(
    document_id: str,
    knowledge_base_id: Annotated[str, Form()],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> UpdateDocumentResponse:
    return await pipeline.update_document(tenant, knowledge_base_id, document_id)


@router.delete("/{document_id}/purge", response_model=PurgeDocumentResponse)
async def purge_document(
    document_id: str,
    knowledge_base_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> PurgeDocumentResponse:
    return await pipeline.purge_document(tenant, knowledge_base_id, document_id)
