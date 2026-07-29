from rag.schemas import RetrievedChunk, TenantContext
from rag.storage.repositories import DocumentRepository


class FakeMappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return list(self.rows)


class FakeSession:
    def __init__(self, result_rows):
        self.result_rows = result_rows
        self.calls = []

    async def execute(self, statement, parameters=None):
        self.calls.append((str(statement), parameters or {}))
        return FakeMappingsResult(self.result_rows)


def tenant():
    return TenantContext(tenant_id="tenant_a", user_id="user_a")


def candidate(chunk_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text="",
        score=score,
        retrieval_method="vector",
        source={},
        metadata={},
    )


async def test_full_text_search_applies_tenant_kb_document_and_metadata_filters():
    session = FakeSession(
        [
            {
                "id": "chunk_1",
                "document_id": "doc_1",
                "score": 0.75,
            }
        ]
    )
    repository = DocumentRepository(session)

    results = await repository.full_text_search(
        tenant(),
        "kb_1",
        "annual leave",
        10,
        document_ids=["doc_1"],
        metadata={"department": "hr"},
    )

    statement, parameters = session.calls[0]
    assert "search_vector" in statement
    assert "document_id = any" in statement.lower()
    assert "metadata @>" in statement.lower()
    assert parameters["tenant_id"] == "tenant_a"
    assert parameters["knowledge_base_id"] == "kb_1"
    assert parameters["document_ids"] == ["doc_1"]
    assert parameters["metadata_filter"] == '{"department": "hr"}'
    assert [item.chunk_id for item in results] == ["chunk_1"]
    assert results[0].retrieval_method == "full_text"


async def test_hydrate_chunks_preserves_candidate_order_and_filters():
    session = FakeSession(
        [
            {
                "id": "chunk_b",
                "document_id": "doc_chunk_b",
                "text": "B",
                "page": 2,
                "metadata": {"department": "hr"},
                "title": "Handbook",
                "source_uri": None,
            },
            {
                "id": "chunk_a",
                "document_id": "doc_chunk_a",
                "text": "A",
                "page": 1,
                "metadata": {"department": "hr"},
                "title": "Handbook",
                "source_uri": None,
            },
        ]
    )
    repository = DocumentRepository(session)

    hydrated = await repository.hydrate_chunks(
        tenant(),
        "kb_1",
        [candidate("chunk_a", 0.9), candidate("chunk_b", 0.8)],
        document_ids=["doc_chunk_a", "doc_chunk_b"],
        metadata={"department": "hr"},
    )

    assert [item.chunk_id for item in hydrated] == ["chunk_a", "chunk_b"]
    assert [item.text for item in hydrated] == ["A", "B"]
    statement, parameters = session.calls[0]
    assert "document_id = any" in statement.lower()
    assert "metadata @>" in statement.lower()
    assert parameters["document_ids"] == ["doc_chunk_a", "doc_chunk_b"]
