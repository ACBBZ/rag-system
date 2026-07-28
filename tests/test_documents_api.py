from fastapi.testclient import TestClient

from app.api.dependencies import get_ingestion_pipeline, get_tenant_context
from app.main import app
from rag.schemas import (
    EmbedDocumentResponse,
    PurgeDocumentResponse,
    TenantContext,
    UpdateDocumentResponse,
)


def test_embed_document_rejects_unlisted_knowledge_base_before_pipeline():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["write"],
    )
    calls = []

    class FakeIngestionPipeline:
        async def embed_document(self, **kwargs):
            calls.append(kwargs)
            return EmbedDocumentResponse(job_id="job_1", document_id="doc_1", status="queued")

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_ingestion_pipeline] = lambda: FakeIngestionPipeline()
    try:
        response = TestClient(app).post(
            "/v1/documents/embed",
            headers={"Authorization": "Bearer valid-key"},
            data={"knowledge_base_id": "kb_2", "title": "Handbook"},
            files={"file": ("handbook.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "knowledge base access denied",
    }
    assert calls == []


def test_embed_document_rejects_missing_write_scope_before_pipeline():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["read"],
    )
    calls = []

    class FakeIngestionPipeline:
        async def embed_document(self, **kwargs):
            calls.append(kwargs)
            return EmbedDocumentResponse(job_id="job_1", document_id="doc_1", status="queued")

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_ingestion_pipeline] = lambda: FakeIngestionPipeline()
    try:
        response = TestClient(app).post(
            "/v1/documents/embed",
            headers={"Authorization": "Bearer valid-key"},
            data={"knowledge_base_id": "kb_1", "title": "Handbook"},
            files={"file": ("handbook.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "missing scope: write",
    }
    assert calls == []


def test_update_document_requires_write_scope():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["read"],
    )
    calls = []

    class FakeIngestionPipeline:
        async def update_document(self, tenant, knowledge_base_id, document_id):
            calls.append((tenant, knowledge_base_id, document_id))
            return UpdateDocumentResponse(
                job_id="job_1",
                document_id=document_id,
                version=2,
                status="queued",
            )

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_ingestion_pipeline] = lambda: FakeIngestionPipeline()
    try:
        response = TestClient(app).patch(
            "/v1/documents/doc_1",
            headers={"Authorization": "Bearer valid-key"},
            data={"knowledge_base_id": "kb_1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "missing scope: write",
    }
    assert calls == []


def test_purge_document_requires_admin_scope():
    tenant = TenantContext(
        tenant_id="tenant_a",
        user_id="user_a",
        knowledge_base_ids=["kb_1"],
        allowed_scopes=["write"],
    )
    calls = []

    class FakeIngestionPipeline:
        async def purge_document(self, tenant, knowledge_base_id, document_id):
            calls.append((tenant, knowledge_base_id, document_id))
            return PurgeDocumentResponse(document_id=document_id, status="purged")

    async def fake_tenant_context():
        return tenant

    app.dependency_overrides[get_tenant_context] = fake_tenant_context
    app.dependency_overrides[get_ingestion_pipeline] = lambda: FakeIngestionPipeline()
    try:
        response = TestClient(app).delete(
            "/v1/documents/doc_1/purge?knowledge_base_id=kb_1",
            headers={"Authorization": "Bearer valid-key"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "error": "forbidden",
        "message": "missing scope: admin",
    }
    assert calls == []
