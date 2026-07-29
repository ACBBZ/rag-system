from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from rag.evaluation.client import RAGApiClient
from rag.evaluation.deterministic_metrics import (
    hit_rate_at_k,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}") from exc
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
            Faithfulness,
            FactualCorrectness,
        )
    except ImportError as exc:
        raise RuntimeError("install the evaluation dependencies with '.[eval]'") from exc

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
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
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
    reference = str(case.get("reference") or "")
    if not reference:
        return {}

    results = await asyncio.gather(
        metrics["faithfulness"].ascore(
            user_input=case["user_input"],
            response=response,
            retrieved_contexts=contexts,
        ),
        metrics["answer_relevancy"].ascore(
            user_input=case["user_input"],
            response=response,
        ),
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
    )
    names = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "factual_correctness",
    ]
    return {name: float(result.value) for name, result in zip(names, results, strict=True)}


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
    retrieved_ids = [chunk["chunk_id"] for chunk in api_result["chunks"]]
    contexts = [chunk["text"] for chunk in api_result["chunks"]]
    relevant_ids = list(case.get("reference_context_ids", []))
    response = str(api_result.get("answer") or "")

    metrics: dict[str, float] = {
        "hit_rate_at_5": hit_rate_at_k(retrieved_ids, relevant_ids, 5),
        "precision_at_5": precision_at_k(retrieved_ids, relevant_ids, 5),
        "recall_at_5": recall_at_k(retrieved_ids, relevant_ids, 5),
        "mrr": mean_reciprocal_rank(retrieved_ids, relevant_ids),
    }
    if ragas_metrics is not None:
        metrics.update(await score_with_ragas(ragas_metrics, case, response, contexts))

    return {
        "case_id": case["case_id"],
        "response": response,
        "retrieved_context_ids": retrieved_ids,
        "trace_id": api_result.get("trace_id"),
        "query_id": api_result.get("query_id"),
        "metrics": metrics,
    }


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

    metric_names = sorted(
        {name for result in results for name in result["metrics"]}
    )
    summary = {
        name: sum(result["metrics"].get(name, 0.0) for result in results) / len(results)
        for name in metric_names
    } if results else {}
    print(json.dumps({"cases": len(results), "metrics": summary}, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the RAG API with JSONL cases")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evals/reports/results.jsonl"))
    parser.add_argument("--base-url", default=os.environ.get("RAG_EVAL_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("RAG_EVAL_API_KEY"), required=False)
    parser.add_argument("--ragas", action="store_true")
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or RAG_EVAL_API_KEY is required")
    return args


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
