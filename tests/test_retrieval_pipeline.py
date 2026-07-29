from types import SimpleNamespace

from rag.retrieval.pipeline import RetrievalPipeline
from rag.schemas import RetrievalOptions, RetrievalSearchRequest, RetrievedChunk, TenantContext


def settings():
    return SimpleNamespace(
        default_query_rewrite_enabled=False,
        default_vector_search_enabled=True,
        default_full_text_search_enabled=False,
        default_hybrid_search_enabled=False,
        default_rerank_enabled=False,
        default_agent_search_enabled=False,
    )


def chunk(chunk_id: str, method: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"text {chunk_id}",
        score=score,
        retrieval_method=method,
        source={},
        metadata={"department": "hr"},
    )


class FakeModelClient:
    def __init__(self):
        self.embed_calls = []
        self.rerank_calls = []
        self.rewrite_calls = []

    async def embed(self, texts):
        self.embed_calls.append(texts)
        return [[0.1, 0.2]]

    async def rewrite(self, query):
        self.rewrite_calls.append(query)
        return f"rewritten {query}"

    async def rerank(self, query, texts):
        self.rerank_calls.append((query, texts))
        return [float(index) for index in range(len(texts), 0, -1)]

    async def answer(self, query, context):
        return "answer", {"prompt_tokens": 10, "completion_tokens": 2}


class FakeVectorStore:
    def __init__(self):
        self.calls = []

    async def search(self, tenant, knowledge_base_id, vector, top_k, document_ids=None):
        self.calls.append(
            {
                "tenant": tenant,
                "knowledge_base_id": knowledge_base_id,
                "vector": vector,
                "top_k": top_k,
                "document_ids": document_ids,
            }
        )
        return [chunk("shared", "vector", 0.9), chunk("vector_only", "vector", 0.8)]


class FakeDocumentRepository:
    def __init__(self):
        self.full_text_calls = []
        self.hydrate_calls = []

    async def full_text_search(
        self,
        tenant,
        knowledge_base_id,
        query,
        top_k,
        document_ids=None,
        metadata=None,
    ):
        self.full_text_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "document_ids": document_ids,
                "metadata": metadata,
            }
        )
        return [chunk("shared", "full_text", 4.0), chunk("lexical_only", "full_text", 3.0)]

    async def hydrate_chunks(
        self,
        tenant,
        knowledge_base_id,
        candidates,
        document_ids=None,
        metadata=None,
    ):
        self.hydrate_calls.append(
            {
                "document_ids": document_ids,
                "metadata": metadata,
                "candidate_ids": [item.chunk_id for item in candidates],
            }
        )
        return candidates


def tenant():
    return TenantContext(tenant_id="tenant_a", user_id="user_a")


async def test_full_text_mode_executes_only_full_text_retrieval():
    models = FakeModelClient()
    vector_store = FakeVectorStore()
    repository = FakeDocumentRepository()
    pipeline = RetrievalPipeline(settings(), models, repository, vector_store)

    response = await pipeline.search(
        tenant(),
        RetrievalSearchRequest(
            knowledge_base_id="kb_1",
            query="leave policy",
            options=RetrievalOptions(retrieval_mode="full_text", final_k=2),
        ),
    )

    assert models.embed_calls == []
    assert vector_store.calls == []
    assert len(repository.full_text_calls) == 1
    assert [item.chunk_id for item in response.chunks] == ["shared", "lexical_only"]
    assert response.effective_options["retrieval_mode"] == "full_text"


async def test_hybrid_mode_executes_both_retrievers_and_passes_filters():
    models = FakeModelClient()
    vector_store = FakeVectorStore()
    repository = FakeDocumentRepository()
    pipeline = RetrievalPipeline(settings(), models, repository, vector_store)

    response = await pipeline.search(
        tenant(),
        RetrievalSearchRequest(
            knowledge_base_id="kb_1",
            query="leave policy",
            options=RetrievalOptions(retrieval_mode="hybrid", top_k=10, final_k=3),
            filters={
                "document_ids": ["doc_shared"],
                "metadata": {"department": "hr"},
            },
        ),
    )

    assert len(models.embed_calls) == 1
    assert vector_store.calls[0]["document_ids"] == ["doc_shared"]
    assert repository.full_text_calls[0]["document_ids"] == ["doc_shared"]
    assert repository.full_text_calls[0]["metadata"] == {"department": "hr"}
    assert repository.hydrate_calls[0]["metadata"] == {"department": "hr"}
    assert response.chunks[0].chunk_id == "shared"
    assert response.chunks[0].retrieval_method == "hybrid"
    assert response.effective_options["retrieval_mode"] == "hybrid"


async def test_query_rewrite_and_rerank_use_effective_options():
    models = FakeModelClient()
    vector_store = FakeVectorStore()
    repository = FakeDocumentRepository()
    pipeline = RetrievalPipeline(settings(), models, repository, vector_store)

    response = await pipeline.search(
        tenant(),
        RetrievalSearchRequest(
            knowledge_base_id="kb_1",
            query="leave",
            options=RetrievalOptions(
                retrieval_mode="vector",
                query_rewrite=True,
                rerank=True,
                final_k=2,
            ),
        ),
    )

    assert models.rewrite_calls == ["leave"]
    assert models.embed_calls == [["rewritten leave"]]
    assert models.rerank_calls[0][0] == "rewritten leave"
    assert response.rewritten_query == "rewritten leave"
    assert response.chunks[0].retrieval_method.endswith("_rerank")
