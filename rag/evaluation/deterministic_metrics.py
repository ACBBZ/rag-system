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
    hits = sum(item in relevant_set for item in candidates)
    return hits / len(candidates)


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = len(set(_top_k(retrieved, k)) & relevant_set)
    return hits / len(relevant_set)


def mean_reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0
