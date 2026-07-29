from types import SimpleNamespace

import httpx
import pytest

from rag.runtime import RuntimeResources
from rag.models.endpoints import ModelEndpointClient


def test_runtime_resources_reuse_shared_clients():
    runtime = RuntimeResources(
        engine=object(),
        sessionmaker=object(),
        http_client=object(),
        milvus_client=object(),
        minio_client=object(),
    )
    assert runtime.http_client is runtime.http_client
    assert runtime.milvus_client is runtime.milvus_client


@pytest.mark.asyncio
async def test_model_client_retries_retryable_status_and_validates_embeddings():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    settings = SimpleNamespace(
        embedding_url="https://models.test/v1/embeddings",
        embedding_api_key="key",
        embedding_model="embed",
        model_max_attempts=2,
        model_retry_backoff_seconds=0.0,
        milvus_vector_dimension=2,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ModelEndpointClient(settings, http_client=http_client)
        assert await client.embed(["hello"]) == [[0.1, 0.2]]

    assert attempts == 2
