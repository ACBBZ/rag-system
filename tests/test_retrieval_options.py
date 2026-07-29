from types import SimpleNamespace

import pytest

from rag.errors import ValidationError
from rag.retrieval.options import resolve_retrieval_options
from rag.schemas import RetrievalOptions


def settings(**overrides):
    values = {
        "default_query_rewrite_enabled": False,
        "default_vector_search_enabled": True,
        "default_full_text_search_enabled": False,
        "default_hybrid_search_enabled": False,
        "default_rerank_enabled": False,
        "default_agent_search_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_resolver_uses_application_defaults_for_unspecified_options():
    effective = resolve_retrieval_options(
        settings(
            default_vector_search_enabled=False,
            default_full_text_search_enabled=True,
            default_rerank_enabled=True,
        ),
        RetrievalOptions(),
    )

    assert effective.retrieval_mode == "full_text"
    assert effective.vector_search is False
    assert effective.full_text_search is True
    assert effective.rerank is True


def test_explicit_hybrid_mode_enables_both_retrievers():
    effective = resolve_retrieval_options(
        settings(),
        RetrievalOptions(retrieval_mode="hybrid", top_k=30, final_k=6),
    )

    assert effective.retrieval_mode == "hybrid"
    assert effective.vector_search is True
    assert effective.full_text_search is True
    assert effective.hybrid_search is True
    assert effective.top_k == 30
    assert effective.final_k == 6


def test_explicit_boolean_overrides_application_default():
    effective = resolve_retrieval_options(
        settings(default_query_rewrite_enabled=True),
        RetrievalOptions(query_rewrite=False),
    )

    assert effective.query_rewrite is False


def test_resolver_rejects_requests_with_no_enabled_retriever():
    with pytest.raises(ValidationError, match="at least one retrieval capability"):
        resolve_retrieval_options(
            settings(default_vector_search_enabled=False),
            RetrievalOptions(vector_search=False, full_text_search=False),
        )


def test_resolver_rejects_final_k_greater_than_top_k():
    with pytest.raises(ValidationError, match="final_k cannot exceed top_k"):
        resolve_retrieval_options(
            settings(),
            RetrievalOptions(top_k=3, final_k=4),
        )
