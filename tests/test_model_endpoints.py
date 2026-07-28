import json

import httpx
import pytest
import respx

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient


def settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="miniopass",
        milvus_uri="http://localhost:19530",
        embedding_url="http://models.local/embed",
        embedding_model="embedding-model",
        embedding_api_key="embedding-key",
        rerank_url="http://models.local/rerank",
        rerank_model="rerank-model",
        rerank_api_key="rerank-key",
        query_rewrite_url="http://models.local/rewrite",
        query_rewrite_model="rewrite-model",
        query_rewrite_api_key="rewrite-key",
        llm_url="http://models.local/answer",
        llm_model="answer-model",
        llm_api_key="answer-key",
        ocr_url="http://models.local/ocr",
        ocr_model="ocr-model",
        ocr_api_key="ocr-key",
    )


@pytest.mark.asyncio
@respx.mock
async def test_embed_posts_url_model_and_api_key():
    route = respx.post("http://models.local/embed").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})
    )
    client = ModelEndpointClient(settings())
    vectors = await client.embed(["hello"])

    assert vectors == [[0.1, 0.2]]
    assert route.calls.last.request.headers["authorization"] == "Bearer embedding-key"
    assert json.loads(route.calls.last.request.content)["model"] == "embedding-model"


@pytest.mark.asyncio
@respx.mock
async def test_rerank_returns_scores():
    respx.post("http://models.local/rerank").mock(
        return_value=httpx.Response(200, json={"scores": [0.8, 0.2]})
    )
    client = ModelEndpointClient(settings())
    assert await client.rerank("q", ["a", "b"]) == [0.8, 0.2]
