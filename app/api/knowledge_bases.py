from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import authorize_knowledge_base_access, get_session, get_tenant_context
from rag.authz import KnowledgeBaseRole, Permission, require_permission
from rag.config import get_settings
from rag.errors import NotFoundError, ValidationError
from rag.schemas import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseMemberRequest,
    KnowledgeBaseSummary,
    TenantContext,
)
from rag.storage.repositories import ManagementRepository

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge-bases"])


def _validate_kb_role(role: str) -> KnowledgeBaseRole:
    try:
        return KnowledgeBaseRole(role)
    except ValueError as exc:
        raise ValidationError("invalid knowledge base role") from exc


@router.post("", response_model=KnowledgeBaseSummary, status_code=201)
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KnowledgeBaseSummary:
    require_permission(tenant, Permission.KNOWLEDGE_BASES_CREATE)
    repository = ManagementRepository(session, get_settings())
    knowledge_base_id = await repository.create_knowledge_base(
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        name=request.name,
        description=request.description,
    )
    await repository.audit(
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.user_id,
        actor_api_key_id=tenant.api_key_id,
        action="knowledge_base.created",
        target_type="knowledge_base",
        target_id=knowledge_base_id,
    )
    await session.commit()
    return KnowledgeBaseSummary(
        id=knowledge_base_id,
        tenant_id=tenant.tenant_id,
        name=request.name,
        description=request.description,
        status="active",
        role=KnowledgeBaseRole.ADMIN.value,
    )


@router.put("/{knowledge_base_id}/members/{user_id}", status_code=204)
async def set_knowledge_base_member(
    knowledge_base_id: str,
    user_id: str,
    request: KnowledgeBaseMemberRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    authorize_knowledge_base_access(
        tenant,
        knowledge_base_id,
        Permission.KNOWLEDGE_BASES_MANAGE_MEMBERS,
    )
    role = _validate_kb_role(request.role)
    repository = ManagementRepository(session, get_settings())
    try:
        await repository.set_knowledge_base_member(
            tenant_id=tenant.tenant_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            role=role.value,
            actor_user_id=tenant.user_id,
        )
    except LookupError as exc:
        raise NotFoundError("user not found") from exc
    await repository.audit(
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.user_id,
        actor_api_key_id=tenant.api_key_id,
        action="knowledge_base.member_updated",
        target_type="knowledge_base",
        target_id=knowledge_base_id,
        after_state={"user_id": user_id, "role": role.value},
    )
    await session.commit()
    return Response(status_code=204)
