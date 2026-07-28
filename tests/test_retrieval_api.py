from fastapi.testclient import TestClient

from app.main import app


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
