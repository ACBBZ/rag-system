from __future__ import annotations


class EvaluationGateError(RuntimeError):
    pass


_HARD_ZERO_METRICS = {
    "tenant_leakage_rate",
    "knowledge_base_leakage_rate",
    "unknown_citation_rate",
    "api_error_rate",
}


def compare_to_baseline(
    *,
    candidate: dict[str, float],
    baseline: dict[str, float],
    max_regressions: dict[str, float],
    minimums: dict[str, float] | None = None,
) -> None:
    failures: list[str] = []
    for metric in _HARD_ZERO_METRICS:
        if candidate.get(metric, 0.0) > 0:
            failures.append(
                f"{metric} must be zero, got {candidate[metric]:.6f}"
            )
    if candidate.get("filter_accuracy", 1.0) < 1.0:
        failures.append(
            "filter_accuracy must be 1.0, "
            f"got {candidate['filter_accuracy']:.6f}"
        )
    for metric, allowed_drop in max_regressions.items():
        if metric not in candidate or metric not in baseline:
            continue
        drop = baseline[metric] - candidate[metric]
        if drop > allowed_drop:
            failures.append(
                f"{metric} regressed by {drop:.6f}; "
                f"allowed regression is {allowed_drop:.6f}"
            )
    for metric, minimum in (minimums or {}).items():
        if candidate.get(metric, float("-inf")) < minimum:
            failures.append(f"{metric} is below minimum {minimum:.6f}")
    if failures:
        raise EvaluationGateError("; ".join(failures))
