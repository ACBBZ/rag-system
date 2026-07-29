from __future__ import annotations

import math


def _top_k(items: list[str], k: int) -> list[str]:
    if k <= 0:
        raise ValueError("k must be positive")
    return items[:k]


def hit_rate_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    return float(any(item in relevant_set for item in _top_k(retrieved, k)))


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    candidates = _top_k(retrieved, k)
    relevant_set = set(relevant)
    if not candidates or not relevant_set:
        return 0.0
    return sum(item in relevant_set for item in candidates) / len(candidates)


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    return len(set(_top_k(retrieved, k)) & relevant_set) / len(relevant_set)


def mean_reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved: list[str],
    relevance: dict[str, int | float],
    k: int,
) -> float:
    candidates = _top_k(retrieved, k)
    dcg = sum(
        (2 ** float(relevance.get(item, 0)) - 1) / math.log2(rank + 1)
        for rank, item in enumerate(candidates, start=1)
    )
    ideal = sorted(
        (float(value) for value in relevance.values()),
        reverse=True,
    )[:k]
    idcg = sum(
        (2**value - 1) / math.log2(rank + 1)
        for rank, value in enumerate(ideal, start=1)
    )
    return dcg / idcg if idcg else 0.0


def filter_accuracy(matches: list[bool]) -> float:
    return sum(matches) / len(matches) if matches else 1.0


def tenant_leakage_rate(
    result_tenants: list[str],
    expected_tenant: str,
) -> float:
    if not result_tenants:
        return 0.0
    return sum(value != expected_tenant for value in result_tenants) / len(
        result_tenants
    )


def knowledge_base_leakage_rate(
    result_kbs: list[str],
    expected_kb: str,
) -> float:
    if not result_kbs:
        return 0.0
    return sum(value != expected_kb for value in result_kbs) / len(result_kbs)


def duplicate_rate(items: list[str]) -> float:
    if not items:
        return 0.0
    return (len(items) - len(set(items))) / len(items)


def abstention_accuracy(predicted: list[bool], expected: list[bool]) -> float:
    if len(predicted) != len(expected):
        raise ValueError("predicted and expected abstention counts must match")
    if not expected:
        return 1.0
    return sum(
        left == right
        for left, right in zip(predicted, expected, strict=True)
    ) / len(expected)
