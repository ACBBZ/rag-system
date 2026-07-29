# Service Level Objectives

## Availability

- Retrieval API monthly availability: 99.9%.
- Document enqueue API monthly availability: 99.9%.
- Readiness must fail when PostgreSQL, MinIO, or Milvus is unavailable.

## Latency

- Retrieval without generation: p95 below 1 second.
- Retrieval with rerank and generation: p95 below 5 seconds, excluding explicitly configured long model timeouts.
- Document enqueue: p95 below 500 milliseconds after raw upload completes.

## Quality and safety

- Tenant leakage rate: exactly 0.
- Knowledge-base leakage rate: exactly 0.
- Filter accuracy: exactly 1.0.
- Unknown citation rate: exactly 0.
- Golden-set Recall@5 regression: no more than 0.02 from baseline.
- Faithfulness regression: no more than 0.03 from baseline.

## Alerting

Alert on readiness failures, model error rate, ingestion terminal failures, stale jobs, empty retrieval spikes, abstention spikes, token-cost anomalies, and evaluation gate failures.
