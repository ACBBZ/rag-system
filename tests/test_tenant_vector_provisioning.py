import pytest

from rag.errors import ServiceUnavailableError
from rag.storage.vector_resources import TenantVectorResource
from rag.tenants.provisioning import TenantProvisioningService


class FakeSession:
    def __init__(self, events):
        self.events = events

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")


class FakeManagementRepository:
    def __init__(self, events):
        self.events = events
        self.key_issued = False

    async def create_tenant_bootstrap(self, **kwargs):
        self.events.append("bootstrap")
        return (
            {"id": "ten_1", "slug": "acme", "name": "Acme", "status": "provisioning"},
            {
                "id": "usr_1",
                "tenant_id": "ten_1",
                "email": "owner@example.com",
                "display_name": None,
                "status": "active",
                "role": "tenant_owner",
            },
            "kb_1",
        )

    async def activate_tenant(self, tenant_id):
        self.events.append("tenant_active")

    async def issue_api_key(self, **kwargs):
        self.events.append("key_issued")
        self.key_issued = True
        return {
            "id": "key_1",
            "prefix": "rag_live_key_1",
            "api_key": "rag_live_key_1.secret",
            "expires_at": None,
        }

    async def audit(self, **kwargs):
        self.events.append(kwargs["action"])


class FakeVectorRepository:
    def __init__(self, events):
        self.events = events
        self.resource = TenantVectorResource(
            id="vec_1",
            tenant_id="ten_1",
            logical_alias="rag_t_1_current",
            physical_collection="rag_t_1_v1",
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

    async def create_pending(self, tenant_id, read_mode="tenant_collection"):
        self.events.append("vector_pending")
        return self.resource

    async def mark_creating(self, resource_id):
        self.events.append("vector_creating")

    async def mark_ready(self, resource_id):
        self.events.append("vector_ready")
        self.resource = TenantVectorResource(
            **{**self.resource.__dict__, "status": "ready"}
        )

    async def mark_failed(self, resource_id, error):
        self.events.append("vector_failed")
        self.resource = TenantVectorResource(
            **{**self.resource.__dict__, "status": "failed", "last_error": error}
        )

    async def get_for_version(self, tenant_id, schema_version):
        return self.resource


class FakeCollectionManager:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail

    def ensure_collection(self, resource):
        self.events.append("milvus_ready")
        if self.fail:
            raise RuntimeError("milvus unavailable")


@pytest.mark.asyncio
async def test_initial_key_is_issued_only_after_collection_is_ready():
    events = []
    service = TenantProvisioningService(
        session=FakeSession(events),
        management_repository=FakeManagementRepository(events),
        vector_repository=FakeVectorRepository(events),
        collection_manager=FakeCollectionManager(events),
    )

    result = await service.create_tenant(
        name="Acme",
        slug="acme",
        owner_email="owner@example.com",
        owner_display_name=None,
        default_knowledge_base_name="Default",
    )

    assert result.api_key["id"] == "key_1"
    assert events.index("milvus_ready") < events.index("vector_ready")
    assert events.index("vector_ready") < events.index("tenant_active")
    assert events.index("tenant_active") < events.index("key_issued")


@pytest.mark.asyncio
async def test_failed_collection_creation_is_retryable_and_does_not_issue_key():
    events = []
    management = FakeManagementRepository(events)
    vector_repository = FakeVectorRepository(events)
    service = TenantProvisioningService(
        session=FakeSession(events),
        management_repository=management,
        vector_repository=vector_repository,
        collection_manager=FakeCollectionManager(events, fail=True),
    )

    with pytest.raises(ServiceUnavailableError, match="provisioning failed"):
        await service.create_tenant(
            name="Acme",
            slug="acme",
            owner_email="owner@example.com",
            owner_display_name=None,
            default_knowledge_base_name="Default",
        )

    assert management.key_issued is False
    assert vector_repository.resource.status == "failed"
    assert "tenant_active" not in events
