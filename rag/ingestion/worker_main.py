from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

from rag.config import get_settings
from rag.ingestion.chunker import ChunkingConfig
from rag.ingestion.repository import IngestionRepository
from rag.ingestion.worker import IngestionWorker
from rag.models.endpoints import ModelEndpointClient
from rag.runtime import close_runtime, create_runtime
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.minio_store import MinioObjectStore


async def run(poll_seconds: float, once: bool) -> None:
    settings = get_settings()
    runtime = create_runtime(settings)
    worker_id = f"worker_{uuid4().hex}"
    try:
        while True:
            async with runtime.sessionmaker() as session:  # type: ignore[operator]
                worker = IngestionWorker(
                    repository=IngestionRepository(
                        session,
                        max_attempts=settings.ingestion_max_attempts,
                    ),
                    object_store=MinioObjectStore(
                        settings,
                        client=runtime.minio_client,  # type: ignore[arg-type]
                    ),
                    model_client=ModelEndpointClient(
                        settings,
                        http_client=runtime.http_client,  # type: ignore[arg-type]
                    ),
                    vector_store=MilvusVectorStore(
                        settings,
                        client=runtime.milvus_client,  # type: ignore[arg-type]
                    ),
                    worker_id=worker_id,
                    chunking_config=ChunkingConfig(
                        target_tokens=settings.chunk_target_tokens,
                        max_tokens=settings.chunk_max_tokens,
                        overlap_tokens=settings.chunk_overlap_tokens,
                    ),
                    parser_limits={
                        "max_pdf_pages": settings.max_pdf_pages,
                        "max_image_pixels": settings.max_image_pixels,
                        "max_spreadsheet_rows": settings.max_spreadsheet_rows,
                    },
                )
                processed = await worker.run_once()
                await session.commit()
            if once:
                return
            if not processed:
                await asyncio.sleep(poll_seconds)
    finally:
        await close_runtime(runtime)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the durable RAG ingestion worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.poll_seconds, args.once))


if __name__ == "__main__":
    main()
