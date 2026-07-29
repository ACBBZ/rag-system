from rag.schemas import RetrievedChunk


def rrf_fusion(
    result_sets: list[list[RetrievedChunk]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[RetrievedChunk]:
    active_weights = weights or [1.0 for _ in result_sets]
    if len(active_weights) != len(result_sets):
        raise ValueError("weights must match result set count")

    fusion_scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    raw_scores: dict[str, dict[str, float]] = {}
    retrieval_methods: dict[str, list[str]] = {}

    for index, result_set in enumerate(result_sets):
        weight = active_weights[index]
        for rank, chunk in enumerate(result_set, start=1):
            fusion_scores[chunk.chunk_id] = (
                fusion_scores.get(chunk.chunk_id, 0.0) + weight / (k + rank)
            )
            chunks.setdefault(chunk.chunk_id, chunk)
            raw_scores.setdefault(chunk.chunk_id, {})[chunk.retrieval_method] = chunk.score
            methods = retrieval_methods.setdefault(chunk.chunk_id, [])
            for method in [*chunk.retrieval_methods, chunk.retrieval_method]:
                if method not in methods:
                    methods.append(method)

    ordered = sorted(fusion_scores.items(), key=lambda item: item[1], reverse=True)
    return [
        chunks[chunk_id].model_copy(
            update={
                "score": score,
                "retrieval_method": "hybrid",
                "retrieval_methods": retrieval_methods[chunk_id],
                "scores": {
                    **chunks[chunk_id].scores,
                    **raw_scores[chunk_id],
                    "fusion": score,
                },
            }
        )
        for chunk_id, score in ordered
    ]
