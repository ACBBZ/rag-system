from fastapi.testclient import TestClient

from app.api.dependencies import get_retrieval_pipeline, get_tenant_context
from app.main import app
from rag.schemas import RetrievalSearchResponse, TenantContext


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_retrieval_requires_bearer_token():
    response = TestClient(app).post(
        "/v1/retrieval/search",
        json={"knowledge_base_id": "kb_1", "query": "hello", "options": {"agent_search": False}},
    )
    assert response.status_code == 401


def test_retrieval_search_calls_pipeline_with_authorized_tenant():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["read"],
    )
    calls = []

    class FakeRetrievalPipeline:
        async def search(self, received_tenant, request):
            calls.append((received_tenant, request))
            return RetrievalSearchResponse(
                query_id="qry_1",
                chunks=[],
                citations=[],
            )

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_retrieval_pipeline] = lambda: FakeRetrievalPipeline()
    try:
        response = TestClient(app).post(
            "/v1/retrieval/search",
            headers={"Authorization": "Bearer valid-key"},
            json={
                "knowledge_base_id": "kb_1",
                "query": "hello",
                "options": {"agent_search": False},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["query_id"] == "qry_1"
    assert len(calls) == 1
    assert calls[0][0] == tenant
    assert calls[0][1].knowledge_base_id == "kb_1"


def test_retrieval_search_rejects_unlisted_knowledge_base_before_pipeline():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["read"],
    )
    calls = []

    class FakeRetrievalPipeline:
        async def search(self, received_tenant, request):
            calls.append((received_tenant, request))
            return RetrievalSearchResponse(query_id="qry_1", chunks=[])

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_retrieval_pipeline] = lambda: FakeRetrievalPipeline()
    try:
        response = TestClient(app).post(
            "/v1/retrieval/search",
            headers={"Authorization": "Bearer valid-key"},
            json={
                "knowledge_base_id": "kb_2",
                "query": "hello",
                "options": {"agent_search": False},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "knowledge base access denied",
    }
    assert calls == []


def test_retrieval_search_rejects_missing_read_scope_before_pipeline():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["write"],
    )
    calls = []

    class FakeRetrievalPipeline:
        async def search(self, received_tenant, request):
            calls.append((received_tenant, request))
            return RetrievalSearchResponse(query_id="qry_1", chunks=[])

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_retrieval_pipeline] = lambda: FakeRetrievalPipeline()
    try:
        response = TestClient(app).post(
            "/v1/retrieval/search",
            headers={"Authorization": "Bearer valid-key"},
            json={
                "knowledge_base_id": "kb_1",
                "query": "hello",
                "options": {"agent_search": False},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "missing scope: read",
    }
    assert calls == []
