from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import Counter, Histogram

QUERY_TOTAL = Counter("rag_query_total", "RAG queries", ["mode", "status"])
QUERY_LATENCY = Histogram("rag_query_latency_seconds", "RAG query latency", ["mode"])
MODEL_ERRORS = Counter("rag_model_errors_total", "Model endpoint errors", ["capability"])
INGESTION_JOBS = Counter("rag_ingestion_jobs_total", "Ingestion job terminal states", ["status"])
ABSTENTION_TOTAL = Counter("rag_abstention_total", "Generated answer abstentions", ["reason"])


def configure_tracing() -> None:
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        trace.set_tracer_provider(TracerProvider())


def tracer():
    return trace.get_tracer("rag-system")


@contextmanager
def timed_span(name: str, **attributes: object) -> Iterator[dict[str, float]]:
    started = time.perf_counter()
    with tracer().start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        timing: dict[str, float] = {}
        try:
            yield timing
        finally:
            timing["milliseconds"] = (time.perf_counter() - started) * 1000
