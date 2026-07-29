import pytest

from rag.retrieval.citations import CitationValidationError, validate_citations
from rag.retrieval.context import ContextBudget, build_context
from rag.schemas import GeneratedAnswer, RetrievedChunk


def chunk(chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_1",
        text=text,
        score=0.9,
        retrieval_method="hybrid",
        source={"title": "Handbook", "page": 1},
        metadata={},
    )


def test_context_respects_token_budget_and_marks_untrusted_sources():
    context = build_context(
        [chunk("c1", "alpha " * 100), chunk("c2", "beta " * 100)],
        budget=ContextBudget(max_context_tokens=80),
    )
    assert "<source" in context
    assert 'chunk_id="c1"' in context
    assert "untrusted" in context.lower()


def test_validate_citations_rejects_unknown_chunk_ids():
    generated = GeneratedAnswer(
        answer="answer",
        cited_chunk_ids=["missing"],
        abstained=False,
        abstention_reason=None,
    )
    with pytest.raises(CitationValidationError):
        validate_citations(generated, [chunk("c1", "source")])


def test_validate_citations_returns_only_model_selected_chunks():
    generated = GeneratedAnswer(
        answer="answer",
        cited_chunk_ids=["c2"],
        abstained=False,
        abstention_reason=None,
    )
    citations = validate_citations(generated, [chunk("c1", "one"), chunk("c2", "two")])
    assert [citation.chunk_id for citation in citations] == ["c2"]
