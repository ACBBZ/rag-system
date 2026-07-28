import pytest

from rag.config import Settings
from rag.errors import ServiceUnavailableError
from rag.schemas import TenantContext, TenantVectorRoute
from rag.storage.milvus_schema import build_collection_names
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.tenant_collection_resolver import TenantCollectionResolver


class FakeMilvusClient:
    def __init__(self):
        self.upserts = []
        self.searches = []
        self.deletes = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return [[]]

    def delete(self, **kwargs):
        self.deletes.append(kwargs)


def settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="miniopass",
        milvus_uri="http://localhost:19530",
        milvus_legacy_collection="rag_chunks",
        milvus_vector_dimension=2,
        embedding_url="http://models:8000/v1/embeddings",
        embedding_model="bge-m3",
        embedding_api_key="embed-key",
        rerank_url="http://models:8000/v1/rerank",
        rerank_model="bge-reranker",
        rerank_api_key="rerank-key",
        query_rewrite_url="http://models:8000/v1/chat/completions",
        query_rewrite_model="rewrite-model",
        query_rewrite_api_key="rewrite-key",
        llm_url="http://models:8000/v1/chat/completions",
        llm_model="answer-model",
        llm_api_key="llm-key",
    )


def tenant_route() -> TenantVectorRoute:
    return TenantVectorRoute(
        collection_name="rag_prod_t_abc_current",
        physical_collection="rag_prod_t_abc_v1",
        mode="tenant_collection",
        schema_version=1,
        embedding_model="bge-m3",
        embedding_dimension=2,
    )


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
    route = tenant_route()
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


@pytest.mark.asyncio
async def test_upsert_uses_tenant_alias_and_keeps_tenant_metadata():
    client = FakeMilvusClient()
    store = MilvusVectorStore(settings(), client=client)
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        vector_route=tenant_route(),
    )

    await store.upsert_chunks(tenant, "kb_a", "doc_a", ["chk_a"], [[0.1, 0.2]])

    assert client.upserts[0]["collection_name"] == "rag_prod_t_abc_current"
    assert client.upserts[0]["data"][0]["tenant_id"] == "ten_a"
    assert client.upserts[0]["data"][0]["knowledge_base_id"] == "kb_a"
    assert client.upserts[0]["data"][0]["document_version"] == 1


@pytest.mark.asyncio
async def test_legacy_upsert_uses_shared_collection_without_new_schema_fields():
    client = FakeMilvusClient()
    store = MilvusVectorStore(settings(), client=client)
    tenant = TenantContext(tenant_id="ten_legacy", user_id="usr_legacy")

    await store.upsert_chunks(tenant, "kb_a", "doc_a", ["chk_a"], [[0.1, 0.2]])

    assert client.upserts[0]["collection_name"] == "rag_chunks"
    assert "document_version" not in client.upserts[0]["data"][0]


@pytest.mark.asyncio
async def test_search_and_delete_use_resolved_collection_and_defense_in_depth_filters():
    client = FakeMilvusClient()
    store = MilvusVectorStore(settings(), client=client)
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        vector_route=tenant_route(),
    )

    await store.search(tenant, "kb_a", [0.1, 0.2], 5)
    await store.delete_document(tenant, "kb_a", "doc_a")

    assert client.searches[0]["collection_name"] == "rag_prod_t_abc_current"
    assert 'tenant_id == "ten_a"' in client.searches[0]["filter"]
    assert 'knowledge_base_id == "kb_a"' in client.searches[0]["filter"]
    assert client.deletes[0]["collection_name"] == "rag_prod_t_abc_current"
    assert 'document_id == "doc_a"' in client.deletes[0]["filter"]
