from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from rag.auth import resolve_tenant_context
from rag.authz import Permission, require_permission
from rag.config import get_settings
from rag.errors import NotFoundError, UnauthorizedError
from rag.ingestion.pipeline import IngestionPipeline
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.pipeline import RetrievalPipeline
from rag.schemas import TenantContext
from rag.storage.database import get_async_engine, get_sessionmaker
from rag.storage.identity_repository import DynamicTenantRepository
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.minio_store import MinioObjectStore
from rag.storage.repositories import DocumentRepository, ManagementRepository


async def get_api_key(authorization: str | None = Header(default=None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("missing bearer token")
    return token


async def get_platform_api_key(authorization: str | None = Header(default=None)) -> str:
    token = await get_api_key(authorization)
    expected = get_settings().platform_api_key
    if not expected or token != expected:
        raise UnauthorizedError("invalid platform API key")
    return token


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
    settings = get_settings()
    return await resolve_tenant_context(api_key, DynamicTenantRepository(session, settings))


def get_knowledge_base_role(tenant: TenantContext, knowledge_base_id: str) -> str | None:
    prefix = f"kb:{knowledge_base_id}:"
    for role in tenant.roles:
        if role.startswith(prefix):
            return role.removeprefix(prefix)
    return None


def authorize_knowledge_base_access(
    tenant: TenantContext,
    knowledge_base_id: str,
    permission: Permission,
) -> str | None:
    if not tenant.can_access_knowledge_base(knowledge_base_id):
        raise NotFoundError("knowledge base not found")
    role = get_knowledge_base_role(tenant, knowledge_base_id)
    require_permission(
        tenant,
        permission,
        knowledge_base_id=knowledge_base_id,
        knowledge_base_role=role,
    )
    return role


async def get_management_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ManagementRepository:
    return ManagementRepository(session, get_settings())


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
