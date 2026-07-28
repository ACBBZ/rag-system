from dataclasses import replace

import pytest

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
        self.altered_aliases = []

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

    def alter_alias(self, collection_name, alias):
        self.altered_aliases.append((collection_name, alias))
        self.aliases[alias] = collection_name


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
        schema_fingerprint="fingerprint",
        status="pending",
        read_mode="tenant_collection",
    )


def test_ensure_collection_creates_collection_and_alias(settings):
    client = FakeMilvusClient()
    manager = MilvusCollectionManager(client, settings)

    manager.ensure_collection(resource())

    assert [item[0] for item in client.created] == ["rag_t_a_v1"]
    assert client.created_aliases == [("rag_t_a_v1", "rag_t_a_current")]


def test_ensure_collection_is_idempotent(settings):
    client = FakeMilvusClient()
    manager = MilvusCollectionManager(client, settings)

    manager.ensure_collection(resource())
    manager.ensure_collection(resource())

    assert len(client.created) == 1
    assert len(client.created_aliases) == 1
    assert client.altered_aliases == []


def test_existing_alias_is_reassigned_to_new_collection(settings):
    client = FakeMilvusClient()
    old = resource()
    manager = MilvusCollectionManager(client, settings)
    manager.ensure_collection(old)

    upgraded = replace(old, physical_collection="rag_t_a_v2", schema_version=2)
    manager.ensure_collection(upgraded)

    assert client.altered_aliases == [("rag_t_a_v2", "rag_t_a_current")]


def test_existing_collection_with_wrong_dimension_is_rejected(settings):
    client = FakeMilvusClient()
    client.collections["rag_t_a_v1"] = {
        "collection_name": "rag_t_a_v1",
        "enable_dynamic_field": False,
        "fields": [{"name": "vector", "params": {"dim": 768}}],
    }
    manager = MilvusCollectionManager(client, settings)

    with pytest.raises(ValueError, match="embedding dimension"):
        manager.ensure_collection(resource())
