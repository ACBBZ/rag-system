from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from rag.auth import authorize_knowledge_base, resolve_tenant_context
from rag.authz import Permission, require_permission
from rag.config import get_settings
from rag.errors import NotFoundError, UnauthorizedError
from rag.ingestion.pipeline import IngestionPipeline
from rag.ingestion.repository import IngestionRepository
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.pipeline import RetrievalPipeline
from rag.retrieval.postgres_store import PostgresRetrievalStore
from rag.runtime import RuntimeResources, get_current_runtime
from rag.schemas import TenantContext
from rag.storage.database import get_async_engine, get_sessionmaker
from rag.storage.identity_repository import DynamicTenantRepository
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.minio_store import MinioObjectStore
from rag.storage.repositories import ManagementRepository


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


def _active_runtime() -> RuntimeResources | None:
    return get_current_runtime()


async def get_session() -> AsyncIterator[AsyncSession]:
    runtime = _active_runtime()
    if runtime is not None:
        sessionmaker = runtime.sessionmaker
    else:
        settings = get_settings()
        engine = get_async_engine(settings)
        sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:  # type: ignore[operator]
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


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
    if tenant.api_key_id is None and (tenant.allowed_scopes or tenant.knowledge_base_ids):
        legacy_scope = {
            Permission.RETRIEVAL_READ: "read",
            Permission.DOCUMENTS_CREATE: "write",
            Permission.DOCUMENTS_UPDATE: "write",
            Permission.DOCUMENTS_DELETE: "admin",
            Permission.KNOWLEDGE_BASES_MANAGE_MEMBERS: "admin",
        }.get(permission)
        if legacy_scope:
            authorize_knowledge_base(tenant, knowledge_base_id, required_scope=legacy_scope)
            return None
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


async def get_ingestion_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestionRepository:
    settings = get_settings()
    return IngestionRepository(session, max_attempts=settings.ingestion_max_attempts)


async def get_ingestion_pipeline(
    _tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)]
) -> IngestionPipeline:
    settings = get_settings()
    runtime = _active_runtime()
    model_client = ModelEndpointClient(
        settings,
        http_client=runtime.http_client if runtime is not None else None,  # type: ignore[arg-type]
    )
    return IngestionPipeline(
        model_client=model_client,
        object_store=MinioObjectStore(
            settings,
            client=runtime.minio_client if runtime is not None else None,  # type: ignore[arg-type]
        ),
        vector_store=MilvusVectorStore(
            settings,
            client=runtime.milvus_client if runtime is not None else None,  # type: ignore[arg-type]
        ),
        document_repository=IngestionRepository(
            session,
            max_attempts=settings.ingestion_max_attempts,
        ),
        max_upload_bytes=settings.max_upload_bytes,
    )


async def get_retrieval_pipeline(
    _tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)]
) -> RetrievalPipeline:
    settings = get_settings()
    runtime = _active_runtime()
    return RetrievalPipeline(
        settings=settings,
        model_client=ModelEndpointClient(
            settings,
            http_client=runtime.http_client if runtime is not None else None,  # type: ignore[arg-type]
        ),
        document_repository=PostgresRetrievalStore(session),
        vector_store=MilvusVectorStore(
            settings,
            client=runtime.milvus_client if runtime is not None else None,  # type: ignore[arg-type]
        ),
    )
