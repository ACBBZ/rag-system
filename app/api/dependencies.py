from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from rag.auth import resolve_tenant_context
from rag.config import get_settings
from rag.errors import UnauthorizedError
from rag.ingestion.pipeline import IngestionPipeline
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.pipeline import RetrievalPipeline
from rag.schemas import TenantContext
from rag.storage.database import get_async_engine, get_sessionmaker
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.minio_store import MinioObjectStore
from rag.storage.repositories import DocumentRepository, TenantRepository


async def get_api_key(authorization: str | None = Header(default=None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


async def get_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    engine = get_async_engine(settings)
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        yield session


async def get_tenant_context(
    api_key: Annotated[str, Depends(get_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantContext:
    return await resolve_tenant_context(api_key, TenantRepository(session))


async def get_ingestion_pipeline(
    _tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestionPipeline:
    settings = get_settings()
    model_client = ModelEndpointClient(settings)
    return IngestionPipeline(
        model_client=model_client,
        object_store=MinioObjectStore(settings),
        vector_store=MilvusVectorStore(settings),
        document_repository=DocumentRepository(session),
    )


async def get_retrieval_pipeline(
    _tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetrievalPipeline:
    settings = get_settings()
    model_client = ModelEndpointClient(settings)
    return RetrievalPipeline(
        settings=settings,
        model_client=model_client,
        document_repository=DocumentRepository(session),
        vector_store=MilvusVectorStore(settings),
    )
