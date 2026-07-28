import pytest

from rag.errors import ServiceUnavailableError
from rag.schemas import TenantContext, TenantVectorRoute
from rag.storage.milvus_schema import build_collection_names
from rag.storage.tenant_collection_resolver import TenantCollectionResolver


def test_collection_names_are_stable_and_do_not_expose_tenant_identity():
    first = build_collection_names("ten_acme-customer", "rag_prod", 3)
    second = build_collection_names("ten_acme-customer", "rag_prod", 3)
    other = build_collection_names("ten_other-customer", "rag_prod", 3)

    assert first == second
    assert first != other
    assert "acme" not in first.alias
    assert "customer" not in first.physical
    assert first.alias.endswith("_current")
    assert first.physical.endswith("_v3")


def test_new_tenant_uses_database_loaded_alias():
    route = TenantVectorRoute(
        collection_name="rag_prod_t_abc_current",
        physical_collection="rag_prod_t_abc_v1",
        mode="tenant_collection",
        schema_version=1,
        embedding_model="bge-m3",
        embedding_dimension=1024,
    )
    tenant = TenantContext(tenant_id="ten_a", user_id="usr_a", vector_route=route)

    resolved = TenantCollectionResolver("rag_chunks").resolve(tenant)

    assert resolved == route


def test_legacy_tenant_uses_shared_collection_until_migrated():
    tenant = TenantContext(tenant_id="ten_legacy", user_id="usr_legacy")

    route = TenantCollectionResolver("rag_chunks").resolve(tenant)

    assert route.collection_name == "rag_chunks"
    assert route.physical_collection == "rag_chunks"
    assert route.mode == "shared"


def test_missing_tenant_and_legacy_routes_are_unavailable():
    tenant = TenantContext(tenant_id="ten_a", user_id="usr_a")

    with pytest.raises(ServiceUnavailableError, match="vector collection is not ready"):
        TenantCollectionResolver("").resolve(tenant)
