import pytest

from rag.evaluation.deterministic_metrics import (
    abstention_accuracy,
    duplicate_rate,
    filter_accuracy,
    ndcg_at_k,
    tenant_leakage_rate,
)
from rag.evaluation.gates import EvaluationGateError, compare_to_baseline


def test_extended_deterministic_metrics():
    assert ndcg_at_k(["a", "b", "c"], {"a": 3, "c": 1}, 3) > 0.8
    assert filter_accuracy([True, True, False]) == pytest.approx(2 / 3)
    assert tenant_leakage_rate(["t1", "t1", "t2"], "t1") == pytest.approx(1 / 3)
    assert duplicate_rate(["a", "a", "b"]) == pytest.approx(1 / 3)
    assert abstention_accuracy([True, False], [True, False]) == 1.0


def test_hard_gate_fails_on_tenant_leakage():
    with pytest.raises(EvaluationGateError, match="tenant_leakage_rate"):
        compare_to_baseline(
            candidate={"tenant_leakage_rate": 0.01, "recall_at_5": 0.9},
            baseline={"tenant_leakage_rate": 0.0, "recall_at_5": 0.9},
            max_regressions={"recall_at_5": 0.02},
        )
