from rag.retrieval.fusion import rrf_fusion
from rag.schemas import RetrievedChunk


def chunk(chunk_id: str, score: float, method: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"text {chunk_id}",
        score=score,
        retrieval_method=method,
        source={},
        metadata={},
    )


def test_rrf_fusion_deduplicates_and_prefers_consistent_hits():
    fused = rrf_fusion(
        [
            [chunk("a", 1.0, "vector"), chunk("b", 0.8, "vector")],
            [chunk("b", 1.0, "full_text"), chunk("a", 0.7, "full_text")],
        ]
    )

    assert [item.chunk_id for item in fused] == ["a", "b"]
    assert fused[0].retrieval_method == "hybrid"
