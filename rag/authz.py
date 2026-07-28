from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from enum import StrEnum

from rag.errors import ForbiddenError, UnauthorizedError
from rag.schemas import TenantContext


class TenantRole(StrEnum):
    OWNER = "tenant_owner"
    ADMIN = "tenant_admin"
    MEMBER = "member"


class KnowledgeBaseRole(StrEnum):
    ADMIN = "kb_admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Permission(StrEnum):
    TENANTS_UPDATE = "tenants:update"
    USERS_CREATE = "users:create"
    USERS_READ = "users:read"
    USERS_UPDATE = "users:update"
    USERS_DISABLE = "users:disable"
    USERS_MANAGE_ADMINS = "users:manage_admins"
    API_KEYS_SELF_CREATE = "api_keys:self:create"
    API_KEYS_SELF_REVOKE = "api_keys:self:revoke"
    API_KEYS_MANAGE = "api_keys:manage"
    KNOWLEDGE_BASES_CREATE = "knowledge_bases:create"
    KNOWLEDGE_BASES_READ = "knowledge_bases:read"
    KNOWLEDGE_BASES_UPDATE = "knowledge_bases:update"
    KNOWLEDGE_BASES_DELETE = "knowledge_bases:delete"
    KNOWLEDGE_BASES_MANAGE_MEMBERS = "knowledge_bases:manage_members"
    DOCUMENTS_CREATE = "documents:create"
    DOCUMENTS_UPDATE = "documents:update"
    DOCUMENTS_DELETE = "documents:delete"
    RETRIEVAL_READ = "retrieval:read"
    AUDIT_READ = "audit:read"


TENANT_ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.OWNER: frozenset(Permission),
    TenantRole.ADMIN: frozenset(
        {
            Permission.USERS_CREATE,
            Permission.USERS_READ,
            Permission.USERS_UPDATE,
            Permission.USERS_DISABLE,
            Permission.API_KEYS_MANAGE,
            Permission.KNOWLEDGE_BASES_CREATE,
            Permission.KNOWLEDGE_BASES_READ,
            Permission.KNOWLEDGE_BASES_UPDATE,
            Permission.KNOWLEDGE_BASES_DELETE,
            Permission.KNOWLEDGE_BASES_MANAGE_MEMBERS,
            Permission.DOCUMENTS_CREATE,
            Permission.DOCUMENTS_UPDATE,
            Permission.DOCUMENTS_DELETE,
            Permission.RETRIEVAL_READ,
            Permission.AUDIT_READ,
        }
    ),
    TenantRole.MEMBER: frozenset(),
}

KNOWLEDGE_BASE_ROLE_PERMISSIONS: dict[KnowledgeBaseRole, frozenset[Permission]] = {
    KnowledgeBaseRole.ADMIN: frozenset(
        {
            Permission.KNOWLEDGE_BASES_READ,
            Permission.KNOWLEDGE_BASES_UPDATE,
            Permission.KNOWLEDGE_BASES_MANAGE_MEMBERS,
            Permission.DOCUMENTS_CREATE,
            Permission.DOCUMENTS_UPDATE,
            Permission.DOCUMENTS_DELETE,
            Permission.RETRIEVAL_READ,
        }
    ),
    KnowledgeBaseRole.EDITOR: frozenset(
        {
            Permission.KNOWLEDGE_BASES_READ,
            Permission.DOCUMENTS_CREATE,
            Permission.DOCUMENTS_UPDATE,
            Permission.RETRIEVAL_READ,
        }
    ),
    KnowledgeBaseRole.VIEWER: frozenset(
        {Permission.KNOWLEDGE_BASES_READ, Permission.RETRIEVAL_READ}
    ),
}

LEGACY_SCOPE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "read": frozenset({Permission.RETRIEVAL_READ, Permission.KNOWLEDGE_BASES_READ}),
    "write": frozenset(
        {
            Permission.DOCUMENTS_CREATE,
            Permission.DOCUMENTS_UPDATE,
            Permission.RETRIEVAL_READ,
            Permission.KNOWLEDGE_BASES_READ,
        }
    ),
    "admin": frozenset(Permission),
    "audit": frozenset({Permission.AUDIT_READ}),
}


def generate_api_key(key_id: str) -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return f"rag_live_{key_id}.{secret}", secret


def parse_api_key(raw_key: str) -> tuple[str, str]:
    if not raw_key.startswith("rag_live_") or "." not in raw_key:
        raise UnauthorizedError("invalid API key")
    prefix, secret = raw_key.split(".", 1)
    key_id = prefix.removeprefix("rag_live_")
    if not key_id or not secret:
        raise UnauthorizedError("invalid API key")
    return key_id, secret


def hash_api_key_secret(secret: str, pepper: str) -> str:
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER must be configured")
    return hmac.new(pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()


def verify_api_key_secret(secret: str, stored_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_api_key_secret(secret, pepper), stored_hash)


def validate_key_lifecycle(
    *,
    is_active: bool,
    revoked_at: datetime | None,
    expires_at: datetime | None,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    if not is_active or revoked_at is not None:
        raise UnauthorizedError("revoked API key")
    if expires_at is not None and expires_at <= current:
        raise UnauthorizedError("expired API key")


def expand_permissions(values: list[str] | set[str] | frozenset[str]) -> set[str]:
    expanded: set[str] = set()
    for value in values:
        if value in LEGACY_SCOPE_PERMISSIONS:
            expanded.update(permission.value for permission in LEGACY_SCOPE_PERMISSIONS[value])
        else:
            expanded.add(value)
    return expanded


def apply_scope_limit(
    permissions: set[str] | frozenset[str],
    scope_limit: list[str] | None,
) -> set[str]:
    dynamic = set(permissions)
    return dynamic if scope_limit is None else dynamic.intersection(expand_permissions(scope_limit))


def effective_permissions(
    tenant: TenantContext,
    knowledge_base_role: str | None = None,
) -> set[str]:
    try:
        role_permissions = TENANT_ROLE_PERMISSIONS[TenantRole(tenant.tenant_role)]
    except ValueError:
        role_permissions = frozenset()
    permissions = {permission.value for permission in role_permissions}
    permissions.update(expand_permissions(tenant.direct_permissions))
    permissions.update(expand_permissions(tenant.allowed_scopes))
    if knowledge_base_role:
        try:
            kb_permissions = KNOWLEDGE_BASE_ROLE_PERMISSIONS[
                KnowledgeBaseRole(knowledge_base_role)
            ]
        except ValueError:
            kb_permissions = frozenset()
        permissions.update(permission.value for permission in kb_permissions)
    return apply_scope_limit(permissions, tenant.scope_limit)


def require_permission(
    tenant: TenantContext,
    permission: Permission,
    *,
    knowledge_base_id: str | None = None,
    knowledge_base_role: str | None = None,
) -> None:
    if knowledge_base_id is not None and tenant.knowledge_base_limit is not None:
        if knowledge_base_id not in tenant.knowledge_base_limit:
            raise ForbiddenError("knowledge base access denied")
    if permission.value not in effective_permissions(tenant, knowledge_base_role):
        raise ForbiddenError(f"missing permission: {permission.value}")
