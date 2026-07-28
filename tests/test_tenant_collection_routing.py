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
        milvus_vector_dimension=2,
        milvus_metric_type="L2",
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
        collection_alias="rag_prod_t_abc_current",
        physical_collection="rag_prod_t_abc_v1",
        embedding_model="bge-m3",
        embedding_dimension=2,
        metric_type="COSINE",
        index_type="HNSW",
        search_params={"ef": 80},
    )


def test_collection_names_are_stable_fixed_v1_and_do_not_expose_tenant_identity():
    first = build_collection_names("ten_acme-customer", "rag_prod")
    second = build_collection_names("ten_acme-customer", "rag_prod")
    other = build_collection_names("ten_other-customer", "rag_prod")

    assert first == second
    assert first != other
    assert "acme" not in first.alias
    assert "customer" not in first.physical
    assert first.alias.endswith("_current")
    assert first.physical.endswith("_v1")


def test_authenticated_tenant_uses_database_loaded_alias():
    route = tenant_route()
    tenant = TenantContext(tenant_id="ten_a", user_id="usr_a", vector_route=route)

    assert TenantCollectionResolver().resolve(tenant) == route


def test_tenant_without_ready_vector_resource_is_unavailable():
    tenant = TenantContext(tenant_id="ten_a", user_id="usr_a")

    with pytest.raises(ServiceUnavailableError, match="vector collection is not ready"):
        TenantCollectionResolver().resolve(tenant)


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

    assert len(client.upserts) == 1
    assert client.upserts[0]["collection_name"] == "rag_prod_t_abc_current"
    assert client.upserts[0]["data"][0]["tenant_id"] == "ten_a"
    assert client.upserts[0]["data"][0]["knowledge_base_id"] == "kb_a"
    assert client.upserts[0]["data"][0]["document_version"] == 1


@pytest.mark.asyncio
async def test_search_uses_route_search_configuration_and_defense_in_depth_filters():
    client = FakeMilvusClient()
    store = MilvusVectorStore(settings(), client=client)
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        vector_route=tenant_route(),
    )

    await store.search(tenant, "kb_a", [0.1, 0.2], 5)

    call = client.searches[0]
    assert call["collection_name"] == "rag_prod_t_abc_current"
    assert call["search_params"] == {
        "metric_type": "COSINE",
        "params": {"ef": 80},
    }
    assert 'tenant_id == "ten_a"' in call["filter"]
    assert 'knowledge_base_id == "kb_a"' in call["filter"]


@pytest.mark.asyncio
async def test_delete_uses_alias_and_tenant_knowledge_base_document_filters():
    client = FakeMilvusClient()
    store = MilvusVectorStore(settings(), client=client)
    tenant = TenantContext(
        tenant_id="ten_a",
        user_id="usr_a",
        vector_route=tenant_route(),
    )

    await store.delete_document(tenant, "kb_a", "doc_a")

    assert len(client.deletes) == 1
    call = client.deletes[0]
    assert call["collection_name"] == "rag_prod_t_abc_current"
    assert 'tenant_id == "ten_a"' in call["filter"]
    assert 'knowledge_base_id == "kb_a"' in call["filter"]
    assert 'document_id == "doc_a"' in call["filter"]
