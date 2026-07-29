from types import SimpleNamespace

import pytest

from rag.ingestion.jobs import IngestionJobStatus
from rag.ingestion.worker import IngestionWorker


def test_ingestion_status_has_complete_state_machine():
    assert [status.value for status in IngestionJobStatus] == [
        "queued",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "validating",
        "activating",
        "completed",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
    ]


@pytest.mark.asyncio
async def test_worker_claims_and_completes_one_job():
    calls = []

    class Repository:
        async def claim_next_job(self, worker_id):
            calls.append(("claim", worker_id))
            return SimpleNamespace(
                job_id="job_1",
                tenant_id="tenant_1",
                knowledge_base_id="kb_1",
                document_id="doc_1",
                document_version=1,
                raw_object_key="raw/doc.txt",
                filename="doc.txt",
                metadata={},
            )

        async def set_job_stage(self, job_id, stage, **kwargs):
            calls.append(("stage", job_id, stage))

        async def replace_staging_chunks(self, *args, **kwargs):
            calls.append(("chunks",))

        async def activate_document_version(self, *args, **kwargs):
            calls.append(("activate",))

    class ObjectStore:
        def get_bytes(self, key):
            return b"hello world"

    class ModelClient:
        async def embed(self, texts):
            return [[0.1, 0.2] for _ in texts]

    class VectorStore:
        async def upsert_chunks(self, *args, **kwargs):
            calls.append(("vectors",))

    worker = IngestionWorker(
        repository=Repository(),
        object_store=ObjectStore(),
        model_client=ModelClient(),
        vector_store=VectorStore(),
        worker_id="worker_1",
    )
    assert await worker.run_once() is True
    assert ("activate",) in calls
    assert ("stage", "job_1", "completed") in calls
