from datetime import UTC, datetime, timedelta

import pytest

from rag.authz import (
    Permission,
    apply_scope_limit,
    generate_api_key,
    hash_api_key_secret,
    parse_api_key,
    require_permission,
    validate_key_lifecycle,
    verify_api_key_secret,
)
from rag.errors import ForbiddenError, UnauthorizedError
from rag.schemas import TenantContext


def test_generated_api_key_can_be_parsed_and_verified():
    raw_key, secret = generate_api_key("key_abc")
    key_id, supplied_secret = parse_api_key(raw_key)
    digest = hash_api_key_secret(secret, "test-pepper")

    assert key_id == "key_abc"
    assert supplied_secret == secret
    assert verify_api_key_secret(supplied_secret, digest, "test-pepper")
    assert not verify_api_key_secret("wrong", digest, "test-pepper")


def test_api_key_scope_limit_only_reduces_permissions():
    permissions = {Permission.RETRIEVAL_READ.value, Permission.DOCUMENTS_CREATE.value}

    assert apply_scope_limit(permissions, [Permission.RETRIEVAL_READ.value]) == {
        Permission.RETRIEVAL_READ.value
    }
    assert apply_scope_limit(permissions, [Permission.USERS_CREATE.value]) == set()


def test_expired_and_revoked_keys_are_rejected():
    now = datetime.now(UTC)
    with pytest.raises(UnauthorizedError, match="expired API key"):
        validate_key_lifecycle(
            is_active=True,
            revoked_at=None,
            expires_at=now - timedelta(seconds=1),
            now=now,
        )
    with pytest.raises(UnauthorizedError, match="revoked API key"):
        validate_key_lifecycle(
            is_active=False,
            revoked_at=now,
            expires_at=None,
            now=now,
        )


def test_member_direct_grant_allows_knowledge_base_creation():
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        api_key_id="key_a",
        tenant_role="member",
        direct_permissions=[Permission.KNOWLEDGE_BASES_CREATE.value],
    )

    require_permission(tenant, Permission.KNOWLEDGE_BASES_CREATE)


def test_api_key_limit_blocks_permission_user_otherwise_has():
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        api_key_id="key_a",
        tenant_role="tenant_owner",
        scope_limit=[Permission.RETRIEVAL_READ.value],
    )

    with pytest.raises(ForbiddenError, match="documents:create"):
        require_permission(tenant, Permission.DOCUMENTS_CREATE)


def test_editor_acl_allows_write_but_not_delete():
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        api_key_id="key_a",
        tenant_role="member",
        knowledge_base_ids=["kb_a"],
        roles=["kb:kb_a:editor"],
    )

    require_permission(
        tenant,
        Permission.DOCUMENTS_CREATE,
        knowledge_base_id="kb_a",
        knowledge_base_role="editor",
    )
    with pytest.raises(ForbiddenError, match="documents:delete"):
        require_permission(
            tenant,
            Permission.DOCUMENTS_DELETE,
            knowledge_base_id="kb_a",
            knowledge_base_role="editor",
        )
