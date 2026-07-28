from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_context
from rag.authz import Permission, TenantRole, require_permission
from rag.config import get_settings
from rag.errors import ForbiddenError, NotFoundError, ValidationError
from rag.schemas import (
    ApiKeyCreated,
    CreateApiKeyRequest,
    CreateUserRequest,
    PermissionGrantRequest,
    TenantContext,
    UpdateUserRoleRequest,
    UserSummary,
)
from rag.storage.repositories import ManagementRepository

router = APIRouter(prefix="/v1", tags=["management"])


def _validate_role(role: str) -> TenantRole:
    try:
        return TenantRole(role)
    except ValueError as exc:
        raise ValidationError("invalid tenant role") from exc


def _check_role_delegation(actor: TenantContext, requested: TenantRole) -> None:
    actor_role = _validate_role(actor.tenant_role)
    if actor_role == TenantRole.OWNER:
        return
    if actor_role == TenantRole.ADMIN and requested == TenantRole.MEMBER:
        return
    raise ForbiddenError("cannot delegate requested tenant role")


async def _get_target_role(session: AsyncSession, tenant_id: str, user_id: str) -> str | None:
    result = await session.execute(
        text(
            """
            select role from user_memberships
            where tenant_id = :tenant_id and user_id = :user_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    )
    return result.scalar_one_or_none()


@router.post("/users", response_model=UserSummary, status_code=201)
async def create_user(
    request: CreateUserRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserSummary:
    require_permission(tenant, Permission.USERS_CREATE)
    role = _validate_role(request.role)
    _check_role_delegation(tenant, role)
    repository = ManagementRepository(session, get_settings())
    try:
        user = await repository.create_user(
            tenant_id=tenant.tenant_id,
            email=request.email,
            display_name=request.display_name,
            role=role.value,
            actor_user_id=tenant.user_id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValidationError("user email already exists in tenant") from exc
    return UserSummary(**user)


@router.patch("/users/{user_id}/role", status_code=204)
async def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    require_permission(tenant, Permission.USERS_UPDATE)
    role = _validate_role(request.role)
    _check_role_delegation(tenant, role)
    if user_id == tenant.user_id:
        raise ForbiddenError("cannot change your own tenant role")
    target_role = await _get_target_role(session, tenant.tenant_id, user_id)
    if target_role is None:
        raise NotFoundError("user not found")
    if tenant.tenant_role == TenantRole.ADMIN and target_role != TenantRole.MEMBER:
        raise ForbiddenError("tenant administrators can only manage members")
    repository = ManagementRepository(session, get_settings())
    try:
        await repository.update_user_role(
            tenant_id=tenant.tenant_id,
            user_id=user_id,
            role=role.value,
            actor_user_id=tenant.user_id,
        )
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise NotFoundError("user not found") from exc
    except ValueError as exc:
        await session.rollback()
        raise ValidationError(str(exc)) from exc
    return Response(status_code=204)


@router.put("/users/{user_id}/scope-grants", status_code=204)
async def grant_user_permission(
    user_id: str,
    request: PermissionGrantRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    require_permission(tenant, Permission.USERS_UPDATE)
    try:
        permission = Permission(request.permission)
    except ValueError as exc:
        raise ValidationError("invalid permission") from exc
    require_permission(tenant, permission)
    if tenant.tenant_role != TenantRole.OWNER and permission == Permission.USERS_MANAGE_ADMINS:
        raise ForbiddenError("only tenant owners can grant administrator management")
    if await _get_target_role(session, tenant.tenant_id, user_id) is None:
        raise NotFoundError("user not found")
    repository = ManagementRepository(session, get_settings())
    await repository.grant_permission(
        tenant_id=tenant.tenant_id,
        user_id=user_id,
        permission=permission.value,
        actor_user_id=tenant.user_id,
        expires_at=request.expires_at,
    )
    await session.commit()
    return Response(status_code=204)


@router.delete("/users/{user_id}/scope-grants/{permission}", status_code=204)
async def revoke_user_permission(
    user_id: str,
    permission: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    require_permission(tenant, Permission.USERS_UPDATE)
    try:
        parsed = Permission(permission)
    except ValueError as exc:
        raise ValidationError("invalid permission") from exc
    if await _get_target_role(session, tenant.tenant_id, user_id) is None:
        raise NotFoundError("user not found")
    repository = ManagementRepository(session, get_settings())
    await repository.revoke_permission(tenant.tenant_id, user_id, parsed.value)
    await session.commit()
    return Response(status_code=204)


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_own_api_key(
    request: CreateApiKeyRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyCreated:
    try:
        require_permission(tenant, Permission.API_KEYS_SELF_CREATE)
    except ForbiddenError:
        require_permission(tenant, Permission.API_KEYS_MANAGE)
    repository = ManagementRepository(session, get_settings())
    key = await repository.issue_api_key(
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        name=request.name,
        scope_limit=request.scope_limit,
        knowledge_base_limit=request.knowledge_base_limit,
        expires_at=request.expires_at,
        created_by_user_id=tenant.user_id,
    )
    await session.commit()
    return ApiKeyCreated(**key)


@router.post("/users/{user_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_user_api_key(
    user_id: str,
    request: CreateApiKeyRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyCreated:
    require_permission(tenant, Permission.API_KEYS_MANAGE)
    if await _get_target_role(session, tenant.tenant_id, user_id) is None:
        raise NotFoundError("user not found")
    repository = ManagementRepository(session, get_settings())
    key = await repository.issue_api_key(
        tenant_id=tenant.tenant_id,
        user_id=user_id,
        name=request.name,
        scope_limit=request.scope_limit,
        knowledge_base_limit=request.knowledge_base_limit,
        expires_at=request.expires_at,
        created_by_user_id=tenant.user_id,
    )
    await session.commit()
    return ApiKeyCreated(**key)


@router.delete("/api-keys/{api_key_id}", status_code=204)
async def revoke_api_key(
    api_key_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    if api_key_id != tenant.api_key_id:
        require_permission(tenant, Permission.API_KEYS_MANAGE)
    repository = ManagementRepository(session, get_settings())
    changed = await repository.revoke_api_key(
        tenant_id=tenant.tenant_id,
        api_key_id=api_key_id,
        actor_user_id=tenant.user_id,
        reason="revoked through API",
    )
    if not changed:
        raise NotFoundError("API key not found")
    await session.commit()
    return Response(status_code=204)
