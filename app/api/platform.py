from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pymilvus import MilvusClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_platform_api_key, get_session
from rag.config import get_settings
from rag.errors import NotFoundError, ServiceUnavailableError, ValidationError
from rag.schemas import (
    ApiKeyCreated,
    CreateTenantRequest,
    CreateTenantResponse,
    TenantSummary,
    UserSummary,
    VectorResourceSummary,
)
from rag.storage.milvus_collection_manager import MilvusCollectionManager
from rag.storage.tenant_provisioning_repository import TenantProvisioningRepository
from rag.storage.vector_resources import VectorResourceRepository
from rag.tenants.provisioning import TenantProvisioningService

router = APIRouter(prefix="/v1/platform", tags=["platform"])


class RetryVectorResourceResponse(BaseModel):
    vector_resource: VectorResourceSummary
    api_key: ApiKeyCreated | None = None


def _provisioning_service(session: AsyncSession) -> TenantProvisioningService:
    settings = get_settings()
    client = MilvusClient(uri=settings.milvus_uri)
    manager = MilvusCollectionManager(client, settings)
    return TenantProvisioningService(
        session=session,
        management_repository=TenantProvisioningRepository(session, settings),
        vector_repository=VectorResourceRepository(session, settings),
        collection_manager=manager,
    )


@router.post("/tenants", response_model=CreateTenantResponse, status_code=201)
async def create_tenant(
    request: CreateTenantRequest,
    _platform_key: Annotated[str, Depends(get_platform_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreateTenantResponse:
    try:
        result = await _provisioning_service(session).create_tenant(
            name=request.name,
            slug=request.slug,
            owner_email=request.owner_email,
            owner_display_name=request.owner_display_name,
            default_knowledge_base_name=request.default_knowledge_base_name,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationError("tenant slug or owner email already exists") from exc
    if result.api_key is None:
        raise ServiceUnavailableError("initial tenant API key was not issued")
    return CreateTenantResponse(
        tenant=TenantSummary(**result.tenant),
        owner=UserSummary(**result.owner),
        knowledge_base_id=result.knowledge_base_id,
        api_key=ApiKeyCreated(**result.api_key),
        vector_resource=VectorResourceSummary(**result.vector_resource.to_summary()),
    )


@router.get(
    "/tenants/{tenant_id}/vector-resource",
    response_model=VectorResourceSummary,
)
async def get_vector_resource(
    tenant_id: str,
    _platform_key: Annotated[str, Depends(get_platform_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VectorResourceSummary:
    resource = await VectorResourceRepository(session, get_settings()).get(tenant_id)
    if resource is None:
        raise NotFoundError("tenant vector resource not found")
    return VectorResourceSummary(**resource.to_summary())


@router.post(
    "/tenants/{tenant_id}/vector-resource/retry",
    response_model=RetryVectorResourceResponse,
)
async def retry_vector_resource(
    tenant_id: str,
    _platform_key: Annotated[str, Depends(get_platform_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetryVectorResourceResponse:
    result = await _provisioning_service(session).retry_vector_resource(tenant_id)
    return RetryVectorResourceResponse(
        vector_resource=VectorResourceSummary(**result.vector_resource.to_summary()),
        api_key=ApiKeyCreated(**result.api_key) if result.api_key else None,
    )
