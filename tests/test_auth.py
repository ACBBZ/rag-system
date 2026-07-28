import pytest

from rag.auth import authorize_knowledge_base, resolve_tenant_context
from rag.errors import ForbiddenError, UnauthorizedError
from rag.schemas import TenantContext


class FakeTenantRepository:
    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        if api_key == "valid-key":
            return TenantContext(
                tenant_id="tenant_a",
                organization_id="org_a",
                user_id="user_a",
                knowledge_base_ids=["kb_a"],
                roles=["admin"],
                allowed_scopes=["read", "write", "admin", "audit"],
            )
        return None


@pytest.mark.asyncio
async def test_resolve_tenant_context_accepts_valid_key():
    context = await resolve_tenant_context("valid-key", FakeTenantRepository())
    assert context.tenant_id == "tenant_a"
    assert "kb_a" in context.knowledge_base_ids


@pytest.mark.asyncio
async def test_resolve_tenant_context_rejects_invalid_key():
    with pytest.raises(UnauthorizedError):
        await resolve_tenant_context("bad-key", FakeTenantRepository())


def test_authorize_knowledge_base_rejects_unlisted_knowledge_base():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_a"],
        allowed_scopes=["read"],
    )

    with pytest.raises(ForbiddenError, match="knowledge base access denied"):
        authorize_knowledge_base(tenant, "kb_b", required_scope="read")


def test_authorize_knowledge_base_rejects_missing_scope():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_a"],
        allowed_scopes=["read"],
    )

    with pytest.raises(ForbiddenError, match="missing scope: admin"):
        authorize_knowledge_base(tenant, "kb_a", required_scope="admin")


def test_authorize_knowledge_base_allows_listed_knowledge_base_with_scope():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_a"],
        allowed_scopes=["read"],
    )

    authorize_knowledge_base(tenant, "kb_a", required_scope="read")
