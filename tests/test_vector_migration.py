import pytest

from rag.config import Settings
from rag.storage.vector_migration import TenantVectorMigrationService
from rag.storage.vector_resources import TenantVectorResource


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class FakeIterator:
    def __init__(self, batches):
        self.batches = list(batches)
        self.closed = False

    def next(self):
        return self.batches.pop(0) if self.batches else []

    def close(self):
        self.closed = True


class FakeMilvusClient:
    def __init__(self, batches):
        self.iterator = FakeIterator(batches)
        self.query_calls = []
        self.upserts = []

    def query_iterator(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.iterator

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class FakeVectorRepository:
    def __init__(self):
        self.resource = TenantVectorResource(
            id="vec_1",
            tenant_id="ten_a",
            logical_alias="rag_t_a_current",
            physical_collection="rag_t_a_v1",
            schema_version=1,
            embedding_model="bge-m3",
            embedding_dimension=2,
            metric_type="COSINE",
            index_type="HNSW",
            index_params={"M": 16, "efConstruction": 200},
            schema_fingerprint="fingerprint",
            status="pending",
            read_mode="shared",
        )
        self.events = []

    async def get_latest(self, tenant_id):
        return self.resource

    async def create_pending(self, tenant_id, read_mode="tenant_collection"):
        return self.resource

    async def mark_migrating(self, resource_id):
        self.events.append("migrating")

    async def activate_read_mode(self, resource_id):
        self.events.append("activated")

    async def mark_failed(self, resource_id, error):
        self.events.append("failed")


class FakeMigrationRepository:
    def __init__(self):
        self.events = []
        self.progress = []

    async def get_or_create(self, tenant_id, source_collection, target_collection):
        self.events.append("created")
        return {"id": "mig_1", "status": "pending"}

    async def mark_running(self, migration_id):
        self.events.append("running")

    async def add_progress(self, migration_id, count, last_chunk_id):
        self.progress.append((count, last_chunk_id))

    async def mark_completed(self, migration_id):
        self.events.append("completed")

    async def mark_failed(self, migration_id, error):
        self.events.append("failed")

    async def get(self, tenant_id):
        return {
            "id": "mig_1",
            "tenant_id": tenant_id,
            "source_collection": "rag_chunks",
            "target_collection": "rag_t_a_v1",
            "migrated_count": sum(item[0] for item in self.progress),
            "failed_count": 0,
            "status": self.events[-1] if self.events else "pending",
            "last_error": None,
        }


class FakeCollectionManager:
    def __init__(self):
        self.resources = []

    def ensure_collection(self, resource):
        self.resources.append(resource)


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


def source_row():
    return {
        "id": "chk_1",
        "vector": [0.1, 0.2],
        "tenant_id": "ten_a",
        "knowledge_base_id": "kb_a",
        "document_id": "doc_a",
        "chunk_id": "chk_1",
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_backfill_filters_one_tenant_and_activates_after_copy():
    client = FakeMilvusClient([[source_row()]])
    vectors = FakeVectorRepository()
    migrations = FakeMigrationRepository()
    service = TenantVectorMigrationService(
        session=FakeSession(),
        settings=settings(),
        client=client,
        vector_repository=vectors,
        migration_repository=migrations,
        collection_manager=FakeCollectionManager(),
    )

    result = await service.backfill_tenant("ten_a")

    assert client.query_calls[0]["collection_name"] == "rag_chunks"
    assert client.query_calls[0]["filter"] == 'tenant_id == "ten_a"'
    assert client.upserts[0]["collection_name"] == "rag_t_a_v1"
    assert client.upserts[0]["data"][0]["document_version"] == 1
    assert migrations.progress == [(1, "chk_1")]
    assert vectors.events == ["migrating", "activated"]
    assert result["migrated_count"] == 1


@pytest.mark.asyncio
async def test_backfill_failure_keeps_shared_route_and_records_failure():
    client = FakeMilvusClient([[source_row()]])

    def fail_upsert(**kwargs):
        raise RuntimeError("target unavailable")

    client.upsert = fail_upsert
    vectors = FakeVectorRepository()
    migrations = FakeMigrationRepository()
    service = TenantVectorMigrationService(
        session=FakeSession(),
        settings=settings(),
        client=client,
        vector_repository=vectors,
        migration_repository=migrations,
        collection_manager=FakeCollectionManager(),
    )

    with pytest.raises(RuntimeError, match="target unavailable"):
        await service.backfill_tenant("ten_a")

    assert "activated" not in vectors.events
    assert "failed" in vectors.events
    assert "failed" in migrations.events
