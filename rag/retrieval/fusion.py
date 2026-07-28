from rag.schemas import RetrievedChunk


def rrf_fusion(result_sets: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    for results in result_sets:
        for rank, chunk in enumerate(results, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(chunk.chunk_id, chunk)

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fused: list[RetrievedChunk] = []
    for chunk_id, score in ordered:
        chunk = chunks[chunk_id].model_copy(
            update={"score": score, "retrieval_method": "hybrid"}
        )
        fused.append(chunk)
    return fused

