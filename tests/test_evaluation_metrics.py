from rag.evaluation.deterministic_metrics import (
    hit_rate_at_k,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


def test_retrieval_metrics_use_ranked_context_ids():
    retrieved = ["chunk_a", "chunk_b", "chunk_c", "chunk_d"]
    relevant = ["chunk_b", "chunk_d"]

    assert hit_rate_at_k(retrieved, relevant, 1) == 0.0
    assert hit_rate_at_k(retrieved, relevant, 2) == 1.0
    assert precision_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 2) == 0.5
    assert mean_reciprocal_rank(retrieved, relevant) == 0.5


def test_retrieval_metrics_handle_empty_reference_sets():
    assert hit_rate_at_k(["chunk_a"], [], 5) == 0.0
    assert precision_at_k(["chunk_a"], [], 5) == 0.0
    assert recall_at_k(["chunk_a"], [], 5) == 0.0
    assert mean_reciprocal_rank(["chunk_a"], []) == 0.0


def test_precision_uses_actual_returned_count_when_fewer_than_k():
    assert precision_at_k(["chunk_a"], ["chunk_a"], 5) == 1.0
