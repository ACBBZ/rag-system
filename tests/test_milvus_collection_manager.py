import pytest

from rag.config import Settings
from rag.storage.milvus_collection_manager import MilvusCollectionManager
from rag.storage.vector_resources import TenantVectorResource


class FakeIndexParams:
    def __init__(self):
        self.indexes = []

    def add_index(self, **kwargs):
        self.indexes.append(kwargs)


class FakeMilvusClient:
    def __init__(self):
        self.collections = {}
        self.aliases = {}
        self.created = []
        self.created_aliases = []

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def prepare_index_params(self):
        return FakeIndexParams()

    def create_collection(self, collection_name, schema, index_params):
        self.created.append((collection_name, schema, index_params))
        self.collections[collection_name] = {
            "collection_name": collection_name,
            "enable_dynamic_field": False,
            "fields": [
                {"name": "id", "params": {"max_length": 256}},
                {"name": "vector", "params": {"dim": 1024}},
                {"name": "tenant_id", "params": {"max_length": 128}},
                {"name": "knowledge_base_id", "params": {"max_length": 128}},
                {"name": "document_id", "params": {"max_length": 128}},
                {"name": "chunk_id", "params": {"max_length": 256}},
                {"name": "document_version", "params": {}},
                {"name": "is_active", "params": {}},
            ],
        }

    def describe_collection(self, collection_name):
        return self.collections[collection_name]

    def describe_alias(self, alias):
        if alias not in self.aliases:
            raise RuntimeError("alias not found")
        return {"alias": alias, "collection_name": self.aliases[alias]}

    def create_alias(self, collection_name, alias):
        self.created_aliases.append((collection_name, alias))
        self.aliases[alias] = collection_name

    def drop_alias(self, alias):
        self.aliases.pop(alias, None)

    def drop_collection(self, collection_name):
        self.collections.pop(collection_name, None)


def settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="miniopass",
        milvus_uri="http://localhost:19530",
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


def resource() -> TenantVectorResource:
    return TenantVectorResource(
        id="vec_1",
        tenant_id="ten_1",
        logical_alias="rag_t_a_current",
        physical_collection="rag_t_a_v1",
        schema_version=1,
        embedding_model="bge-m3",
        embedding_dimension=1024,
        metric_type="COSINE",
        index_type="HNSW",
        index_params={"M": 16, "efConstruction": 200},
        search_params={"ef": 64},
        schema_fingerprint="fingerprint",
        status="pending",
    )


def test_ensure_collection_creates_collection_and_alias():
    client = FakeMilvusClient()
    manager = MilvusCollectionManager(client, settings())

    manager.ensure_collection(resource())

    assert [item[0] for item in client.created] == ["rag_t_a_v1"]
    assert client.created_aliases == [("rag_t_a_v1", "rag_t_a_current")]


def test_ensure_collection_is_idempotent():
    client = FakeMilvusClient()
    manager = MilvusCollectionManager(client, settings())

    manager.ensure_collection(resource())
    manager.ensure_collection(resource())

    assert len(client.created) == 1
    assert len(client.created_aliases) == 1


def test_existing_alias_pointing_elsewhere_is_rejected():
    client = FakeMilvusClient()
    client.aliases["rag_t_a_current"] = "unexpected_collection"
    manager = MilvusCollectionManager(client, settings())

    with pytest.raises(ValueError, match="unexpected collection"):
        manager.ensure_collection(resource())

    assert client.aliases["rag_t_a_current"] == "unexpected_collection"


def test_existing_collection_with_wrong_dimension_is_rejected():
    client = FakeMilvusClient()
    client.collections["rag_t_a_v1"] = {
        "collection_name": "rag_t_a_v1",
        "enable_dynamic_field": False,
        "fields": [{"name": "vector", "params": {"dim": 768}}],
    }
    manager = MilvusCollectionManager(client, settings())

    with pytest.raises(ValueError, match="embedding dimension"):
        manager.ensure_collection(resource())
