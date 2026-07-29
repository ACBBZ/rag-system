from typing import Literal

from pydantic import BaseModel

from rag.config import Settings
from rag.errors import ValidationError
from rag.schemas import RetrievalOptions


class EffectiveRetrievalOptions(BaseModel):
    retrieval_mode: Literal["vector", "full_text", "hybrid"]
    query_rewrite: bool
    vector_search: bool
    full_text_search: bool
    hybrid_search: bool
    rerank: bool
    agent_search: bool
    top_k: int
    final_k: int
    vector_weight: float
    lexical_weight: float
    rrf_k: int
    rerank_candidate_k: int
    per_document_limit: int
    score_threshold: float | None
    include_diagnostics: bool
    allow_partial_results: bool


def _resolve(value: bool | None, default: bool) -> bool:
    return default if value is None else value


def resolve_retrieval_options(
    settings: Settings,
    options: RetrievalOptions,
) -> EffectiveRetrievalOptions:
    if options.final_k > options.top_k:
        raise ValidationError("final_k cannot exceed top_k")
    query_rewrite = _resolve(
        options.query_rewrite,
        settings.default_query_rewrite_enabled,
    )
    rerank = _resolve(options.rerank, settings.default_rerank_enabled)
    agent_search = _resolve(options.agent_search, settings.default_agent_search_enabled)
    if options.retrieval_mode and options.retrieval_mode != "auto":
        mode = options.retrieval_mode
        vector_search = mode in {"vector", "hybrid"}
        full_text_search = mode in {"full_text", "hybrid"}
        hybrid_search = mode == "hybrid"
    else:
        vector_search = _resolve(
            options.vector_search,
            settings.default_vector_search_enabled,
        )
        full_text_search = _resolve(
            options.full_text_search,
            settings.default_full_text_search_enabled,
        )
        hybrid_requested = _resolve(
            options.hybrid_search,
            settings.default_hybrid_search_enabled,
        )
        if hybrid_requested:
            if options.vector_search is False or options.full_text_search is False:
                raise ValidationError(
                    "hybrid retrieval conflicts with an explicitly disabled retriever"
                )
            vector_search = True
            full_text_search = True
        hybrid_search = vector_search and full_text_search
        if hybrid_search:
            mode = "hybrid"
        elif vector_search:
            mode = "vector"
        elif full_text_search:
            mode = "full_text"
        else:
            raise ValidationError("at least one retrieval capability must be enabled")
    vector_weight = (
        options.vector_weight
        if options.vector_weight is not None
        else float(getattr(settings, "default_vector_weight", 1.0))
    )
    lexical_weight = (
        options.lexical_weight
        if options.lexical_weight is not None
        else float(getattr(settings, "default_lexical_weight", 0.8))
    )
    if hybrid_search and vector_weight == 0 and lexical_weight == 0:
        raise ValidationError("hybrid weights cannot both be zero")
    rrf_k = options.rrf_k or int(getattr(settings, "default_rrf_k", 60))
    rerank_candidate_k = options.rerank_candidate_k or int(
        getattr(settings, "default_rerank_candidate_k", max(options.final_k, 30))
    )
    rerank_candidate_k = min(
        options.top_k,
        max(options.final_k, rerank_candidate_k),
    )
    per_document_limit = options.per_document_limit or int(
        getattr(settings, "default_per_document_limit", 3)
    )
    per_document_limit = min(per_document_limit, options.final_k)
    score_threshold = (
        options.score_threshold
        if options.score_threshold is not None
        else getattr(settings, "default_score_threshold", None)
    )
    return EffectiveRetrievalOptions(
        retrieval_mode=mode,
        query_rewrite=query_rewrite,
        vector_search=vector_search,
        full_text_search=full_text_search,
        hybrid_search=hybrid_search,
        rerank=rerank,
        agent_search=agent_search,
        top_k=options.top_k,
        final_k=options.final_k,
        vector_weight=vector_weight,
        lexical_weight=lexical_weight,
        rrf_k=rrf_k,
        rerank_candidate_k=rerank_candidate_k,
        per_document_limit=per_document_limit,
        score_threshold=score_threshold,
        include_diagnostics=options.include_diagnostics,
        allow_partial_results=options.allow_partial_results,
    )
