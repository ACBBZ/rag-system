from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from rag.evaluation.client import RAGApiClient
from rag.evaluation.deterministic_metrics import (
    duplicate_rate,
    hit_rate_at_k,
    knowledge_base_leakage_rate,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    tenant_leakage_rate,
)
from rag.evaluation.gates import compare_to_baseline


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL at line {line_number}"
                ) from exc
    return cases


async def build_ragas_metrics() -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            FactualCorrectness,
            Faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "install the evaluation dependencies with '.[eval]'"
        ) from exc
    client = AsyncOpenAI(
        api_key=os.environ["RAGAS_EVALUATOR_API_KEY"],
        base_url=os.environ.get("RAGAS_EVALUATOR_BASE_URL"),
    )
    llm = llm_factory(
        os.environ["RAGAS_EVALUATOR_MODEL"],
        provider="openai",
        client=client,
        temperature=0,
    )
    embeddings = embedding_factory(
        "openai",
        model=os.environ["RAGAS_EVALUATOR_EMBEDDING_MODEL"],
        client=client,
    )
    return {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(
            llm=llm,
            embeddings=embeddings,
        ),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "factual_correctness": FactualCorrectness(llm=llm),
    }


async def score_with_ragas(
    metrics: dict[str, Any],
    case: dict[str, Any],
    response: str,
    contexts: list[str],
) -> dict[str, float]:
    tasks: list[Any] = [
        metrics["faithfulness"].ascore(
            user_input=case["user_input"],
            response=response,
            retrieved_contexts=contexts,
        ),
        metrics["answer_relevancy"].ascore(
            user_input=case["user_input"],
            response=response,
        ),
    ]
    names = ["faithfulness", "answer_relevancy"]
    reference = str(case.get("reference") or "")
    if reference:
        tasks.extend(
            [
                metrics["context_precision"].ascore(
                    user_input=case["user_input"],
                    reference=reference,
                    retrieved_contexts=contexts,
                ),
                metrics["context_recall"].ascore(
                    user_input=case["user_input"],
                    reference=reference,
                    retrieved_contexts=contexts,
                ),
                metrics["factual_correctness"].ascore(
                    response=response,
                    reference=reference,
                ),
            ]
        )
        names.extend(
            [
                "context_precision",
                "context_recall",
                "factual_correctness",
            ]
        )
    results = await asyncio.gather(*tasks)
    return {
        name: float(result.value)
        for name, result in zip(names, results, strict=True)
    }


async def evaluate_case(
    client: RAGApiClient,
    case: dict[str, Any],
    ragas_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    api_result = await client.search(
        knowledge_base_id=case["knowledge_base_id"],
        query=case["user_input"],
        options=case.get(
            "options",
            {
                "retrieval_mode": "hybrid",
                "rerank": True,
                "agent_search": True,
            },
        ),
        filters=case.get("filters", {}),
    )
    chunks = api_result["chunks"]
    retrieved_ids = [chunk["chunk_id"] for chunk in chunks]
    contexts = [chunk["text"] for chunk in chunks]
    reference_keys = list(case.get("reference_context_keys", []))
    runtime_keys = [
        str(chunk.get("metadata", {}).get("_context_key", ""))
        for chunk in chunks
    ]
    relevant_ids = list(case.get("reference_context_ids", []))
    metric_retrieved = runtime_keys if reference_keys else retrieved_ids
    metric_relevant = reference_keys if reference_keys else relevant_ids
    response = str(api_result.get("answer") or "")
    relevance = {
        key: int(value)
        for key, value in case.get("reference_relevance", {}).items()
    }
    expected_tenant = str(case.get("tenant_id") or "")
    result_tenants = [
        str(chunk.get("metadata", {}).get("tenant_id") or "")
        for chunk in chunks
    ]
    result_kbs = [
        str(chunk.get("metadata", {}).get("knowledge_base_id") or "")
        for chunk in chunks
    ]
    metrics: dict[str, float] = {
        "hit_rate_at_5": hit_rate_at_k(metric_retrieved, metric_relevant, 5),
        "precision_at_5": precision_at_k(
            metric_retrieved,
            metric_relevant,
            5,
        ),
        "recall_at_5": recall_at_k(metric_retrieved, metric_relevant, 5),
        "mrr": mean_reciprocal_rank(metric_retrieved, metric_relevant),
        "duplicate_rate": duplicate_rate(retrieved_ids),
        "ndcg_at_5": (
            ndcg_at_k(retrieved_ids, relevance, 5) if relevance else 0.0
        ),
        "unknown_citation_rate": float(
            any(
                citation["chunk_id"] not in retrieved_ids
                for citation in api_result.get("citations", [])
            )
        ),
        "abstention_correct": float(
            (api_result.get("answer_status") != "answered")
            == bool(case.get("expected_abstain", False))
        ),
        "tenant_leakage_rate": (
            tenant_leakage_rate(result_tenants, expected_tenant)
            if expected_tenant
            else 0.0
        ),
        "knowledge_base_leakage_rate": knowledge_base_leakage_rate(
            result_kbs,
            case["knowledge_base_id"],
        ),
    }
    if ragas_metrics is not None:
        metrics.update(
            await score_with_ragas(
                ragas_metrics,
                case,
                response,
                contexts,
            )
        )
    return {
        "case_id": case["case_id"],
        "tags": case.get("tags", []),
        "response": response,
        "answer_status": api_result.get("answer_status"),
        "retrieved_context_ids": retrieved_ids,
        "trace_id": api_result.get("trace_id"),
        "query_id": api_result.get("query_id"),
        "metrics": metrics,
    }


def summarize(
    results: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    metric_names = sorted(
        {name for result in results for name in result["metrics"]}
    )
    overall = (
        {
            name: sum(
                result["metrics"].get(name, 0.0) for result in results
            )
            / len(results)
            for name in metric_names
        }
        if results
        else {}
    )
    grouped_values: dict[str, list[dict[str, float]]] = defaultdict(list)
    for result in results:
        for tag in result.get("tags", []):
            grouped_values[tag].append(result["metrics"])
    by_tag: dict[str, dict[str, float]] = {}
    for tag, values in grouped_values.items():
        names = sorted({name for value in values for name in value})
        by_tag[tag] = {
            name: sum(value.get(name, 0.0) for value in values) / len(values)
            for name in names
        }
    return overall, by_tag


async def run(args: argparse.Namespace) -> None:
    cases = load_jsonl(args.dataset)
    ragas_metrics = await build_ragas_metrics() if args.ragas else None
    async with RAGApiClient(args.base_url, args.api_key) as client:
        results = [
            await evaluate_case(client, case, ragas_metrics)
            for case in cases
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    overall, by_tag = summarize(results)
    summary = {"cases": len(results), "metrics": overall, "by_tag": by_tag}
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.baseline:
        baseline = json.loads(
            args.baseline.read_text(encoding="utf-8")
        )["metrics"]
        compare_to_baseline(
            candidate=overall,
            baseline=baseline,
            max_regressions={
                "recall_at_5": 0.02,
                "mrr": 0.02,
                "faithfulness": 0.03,
                "context_precision": 0.03,
            },
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the RAG API with JSONL cases"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/reports/results.jsonl"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("evals/reports/summary.json"),
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RAG_EVAL_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("RAG_EVAL_API_KEY"),
    )
    parser.add_argument("--ragas", action="store_true")
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or RAG_EVAL_API_KEY is required")
    return args


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
