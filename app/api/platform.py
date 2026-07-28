from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_platform_api_key, get_session
from rag.config import get_settings
from rag.errors import ValidationError
from rag.schemas import ApiKeyCreated, CreateTenantRequest, CreateTenantResponse, TenantSummary, UserSummary
from rag.storage.repositories import ManagementRepository

router = APIRouter(prefix="/v1/platform", tags=["platform"])


@router.post("/tenants", response_model=CreateTenantResponse, status_code=201)
async def create_tenant(
    request: CreateTenantRequest,
    _platform_key: Annotated[str, Depends(get_platform_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreateTenantResponse:
    repository = ManagementRepository(session, get_settings())
    try:
        tenant, owner, knowledge_base_id, api_key = await repository.create_tenant(
            name=request.name,
            slug=request.slug,
            owner_email=request.owner_email,
            owner_display_name=request.owner_display_name,
            default_knowledge_base_name=request.default_knowledge_base_name,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationError("tenant slug or owner email already exists") from exc
    return CreateTenantResponse(
        tenant=TenantSummary(**tenant),
        owner=UserSummary(**owner),
        knowledge_base_id=knowledge_base_id,
        api_key=ApiKeyCreated(**api_key),
    )
