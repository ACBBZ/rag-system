from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    authorize_knowledge_base_access,
    get_ingestion_pipeline,
    get_session,
    get_tenant_context,
)
from rag.authz import Permission
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
    session: Annotated[AsyncSession, Depends(get_session)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
    source_uri: Annotated[str | None, Form()] = None,
) -> EmbedDocumentResponse:
    await authorize_knowledge_base_access(
        session, tenant, knowledge_base_id, Permission.DOCUMENTS_CREATE
    )
    content = await file.read()
    response = await pipeline.embed_document(
        tenant=tenant,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or "upload.bin",
        content=content,
        title=title,
        source_uri=source_uri,
        metadata={},
    )
    await session.commit()
    return response


@router.patch("/{document_id}", response_model=UpdateDocumentResponse)
async def update_document(
    document_id: str,
    knowledge_base_id: Annotated[str, Form()],
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> UpdateDocumentResponse:
    await authorize_knowledge_base_access(
        session, tenant, knowledge_base_id, Permission.DOCUMENTS_UPDATE
    )
    response = await pipeline.update_document(tenant, knowledge_base_id, document_id)
    await session.commit()
    return response


@router.delete("/{document_id}/purge", response_model=PurgeDocumentResponse)
async def purge_document(
    document_id: str,
    knowledge_base_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    pipeline: Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)],
) -> PurgeDocumentResponse:
    await authorize_knowledge_base_access(
        session, tenant, knowledge_base_id, Permission.DOCUMENTS_DELETE
    )
    response = await pipeline.purge_document(tenant, knowledge_base_id, document_id)
    await session.commit()
    return response
