from types import SimpleNamespace

from rag.retrieval.options import resolve_retrieval_options
from rag.schemas import RetrievalOptions
from rag.storage.milvus_store import compile_milvus_metadata_filter


def settings():
    return SimpleNamespace(
        default_query_rewrite_enabled=False,
        default_vector_search_enabled=True,
        default_full_text_search_enabled=True,
        default_hybrid_search_enabled=True,
        default_rerank_enabled=True,
        default_agent_search_enabled=True,
        default_vector_weight=1.0,
        default_lexical_weight=0.8,
        default_rrf_k=60,
        default_rerank_candidate_k=30,
        default_per_document_limit=3,
        default_score_threshold=None,
    )


def test_retrieval_controls_are_resolved_and_validated():
    effective = resolve_retrieval_options(
        settings(),
        RetrievalOptions(
            retrieval_mode="hybrid",
            top_k=40,
            final_k=6,
            vector_weight=1.2,
            lexical_weight=0.6,
            rrf_k=50,
            rerank_candidate_k=20,
            per_document_limit=2,
            score_threshold=0.1,
        ),
    )
    assert effective.vector_weight == 1.2
    assert effective.lexical_weight == 0.6
    assert effective.rrf_k == 50
    assert effective.rerank_candidate_k == 20
    assert effective.per_document_limit == 2
    assert effective.score_threshold == 0.1


def test_milvus_metadata_filter_is_safe_and_deterministic():
    expression = compile_milvus_metadata_filter({"department": "hr", "year": 2026})
    assert expression == 'metadata["department"] == "hr" and metadata["year"] == 2026'
