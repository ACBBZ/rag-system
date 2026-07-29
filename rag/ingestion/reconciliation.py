from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class IngestionReconciler:
    def __init__(self, session: AsyncSession, object_store) -> None:
        self.session = session
        self.object_store = object_store

    async def reset_stale_jobs(self, stale_seconds: int) -> int:
        result = await self.session.execute(
            text(
                """
                update ingestion_jobs
                set status = 'failed_retryable', stage = 'failed_retryable',
                    error_code = 'stale_worker',
                    error_message = 'worker heartbeat expired',
                    available_at = now(), updated_at = now()
                where status in (
                    'parsing', 'chunking', 'embedding', 'indexing',
                    'validating', 'activating'
                )
                  and heartbeat_at < now() - (:seconds * interval '1 second')
                """
            ),
            {"seconds": stale_seconds},
        )
        return int(result.rowcount or 0)

    async def missing_raw_objects(self) -> list[str]:
        result = await self.session.execute(
            text(
                """
                select id, raw_object_key from document_versions
                where status in ('staging', 'active')
                """
            )
        )
        missing: list[str] = []
        for row in result.mappings():
            if not self.object_store.object_exists(row["raw_object_key"]):
                missing.append(row["id"])
        return missing
