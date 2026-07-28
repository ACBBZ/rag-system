import pytest

from app.api.dependencies import authorize_knowledge_base_access
from rag.authz import Permission
from rag.errors import NotFoundError
from rag.schemas import TenantContext
from rag.storage.milvus_store import _safe_filter_id


def test_cross_tenant_knowledge_base_is_not_disclosed():
    tenant_a = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        api_key_id="key_a",
        tenant_role="member",
        knowledge_base_ids=["kb_a"],
        roles=["kb:kb_a:viewer"],
    )

    with pytest.raises(NotFoundError, match="knowledge base not found"):
        authorize_knowledge_base_access(
            tenant_a,
            "kb_b",
            Permission.RETRIEVAL_READ,
        )


def test_api_key_knowledge_base_limit_is_applied_after_acl_loading():
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        api_key_id="key_a",
        tenant_role="tenant_admin",
        knowledge_base_ids=["kb_a", "kb_b"],
        knowledge_base_limit=["kb_a"],
    )

    authorize_knowledge_base_access(tenant, "kb_a", Permission.RETRIEVAL_READ)
    with pytest.raises(NotFoundError):
        authorize_knowledge_base_access(tenant, "kb_b", Permission.RETRIEVAL_READ)


def test_milvus_filter_identifiers_reject_expression_injection():
    assert _safe_filter_id("ten_a-123", "tenant_id") == "ten_a-123"
    with pytest.raises(ValueError, match="invalid document_id"):
        _safe_filter_id('doc_a" or tenant_id != "ten_a', "document_id")
