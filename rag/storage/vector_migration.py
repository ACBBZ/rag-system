from __future__ import annotations

import asyncio
from uuid import uuid4

from pymilvus import MilvusClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config import Settings
from rag.errors import NotFoundError, ServiceUnavailableError
from rag.storage.milvus_store import _safe_filter_id


class VectorMigrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        tenant_id: str,
        source_collection: str,
        target_collection: str,
    ) -> dict[str, object]:
        existing = await self.get(tenant_id)
        if existing is not None and existing["target_collection"] == target_collection:
            return existing
        migration_id = f"mig_{uuid4().hex}"
        await self.session.execute(
            text(
                """
                insert into tenant_vector_migrations (
                    id, tenant_id, source_collection, target_collection, status
                ) values (
                    :id, :tenant_id, :source_collection, :target_collection, 'pending'
                )
                on conflict (tenant_id, target_collection) do nothing
                """
            ),
            {
                "id": migration_id,
                "tenant_id": tenant_id,
                "source_collection": source_collection,
                "target_collection": target_collection,
            },
        )
        created = await self.get(tenant_id)
        if created is None:
            raise RuntimeError("failed to create vector migration record")
        return created

    async def get(self, tenant_id: str) -> dict[str, object] | None:
        result = await self.session.execute(
            text(
                """
                select id, tenant_id, source_collection, target_collection,
                       migrated_count, failed_count, status, last_error
                from tenant_vector_migrations
                where tenant_id = :tenant_id
                order by created_at desc
                limit 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def mark_running(self, migration_id: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_migrations
                set status = 'running', last_error = null, updated_at = now()
                where id = :id
                """
            ),
            {"id": migration_id},
        )

    async def add_progress(
        self,
        migration_id: str,
        count: int,
        last_chunk_id: str | None,
    ) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_migrations
                set migrated_count = migrated_count + :count,
                    last_chunk_id = :last_chunk_id,
                    updated_at = now()
                where id = :id
                """
            ),
            {
                "id": migration_id,
                "count": count,
                "last_chunk_id": last_chunk_id,
            },
        )

    async def mark_completed(self, migration_id: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_migrations
                set status = 'completed', last_error = null, updated_at = now()
                where id = :id
                """
            ),
            {"id": migration_id},
        )

    async def mark_failed(self, migration_id: str, error: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_migrations
                set status = 'failed', failed_count = failed_count + 1,
                    last_error = :error, updated_at = now()
                where id = :id
                """
            ),
            {"id": migration_id, "error": error[:4000]},
        )


class TenantVectorMigrationService:
    def __init__(
        self,
        *,
        session,
        settings: Settings,
        client: MilvusClient,
        vector_repository,
        migration_repository,
        collection_manager,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = client
        self.vector_repository = vector_repository
        self.migration_repository = migration_repository
        self.collection_manager = collection_manager

    async def backfill_tenant(self, tenant_id: str) -> dict[str, object]:
        safe_tenant_id = _safe_filter_id(tenant_id, "tenant_id")
        source_collection = self.settings.legacy_milvus_collection
        if not source_collection:
            raise ServiceUnavailableError("legacy Milvus collection is not configured")

        resource = await self.vector_repository.get_latest(tenant_id)
        if resource is None:
            resource = await self.vector_repository.create_pending(
                tenant_id,
                read_mode="shared",
            )
            await self.session.commit()

        await asyncio.to_thread(self.collection_manager.ensure_collection, resource)
        migration = await self.migration_repository.get_or_create(
            tenant_id,
            source_collection,
            resource.physical_collection,
        )
        migration_id = str(migration["id"])
        await self.vector_repository.mark_migrating(resource.id)
        await self.migration_repository.mark_running(migration_id)
        await self.session.commit()

        iterator = None
        try:
            iterator = await asyncio.to_thread(
                self.client.query_iterator,
                collection_name=source_collection,
                batch_size=self.settings.milvus_migration_batch_size,
                filter=f'tenant_id == "{safe_tenant_id}"',
                output_fields=[
                    "id",
                    "vector",
                    "tenant_id",
                    "knowledge_base_id",
                    "document_id",
                    "chunk_id",
                    "is_active",
                ],
            )
            while True:
                batch = await asyncio.to_thread(iterator.next)
                if not batch:
                    break
                rows = [self._normalize_row(item, safe_tenant_id) for item in batch]
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=resource.physical_collection,
                    data=rows,
                )
                last_chunk_id = str(rows[-1]["id"]) if rows else None
                await self.migration_repository.add_progress(
                    migration_id,
                    len(rows),
                    last_chunk_id,
                )
                await self.session.commit()

            await self.migration_repository.mark_completed(migration_id)
            await self.vector_repository.activate_read_mode(resource.id)
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            await self.migration_repository.mark_failed(migration_id, str(exc))
            await self.vector_repository.mark_failed(resource.id, str(exc))
            await self.session.commit()
            raise
        finally:
            if iterator is not None:
                await asyncio.to_thread(iterator.close)

        completed = await self.migration_repository.get(tenant_id)
        if completed is None:
            raise NotFoundError("vector migration not found")
        return completed

    @staticmethod
    def _normalize_row(item, tenant_id: str) -> dict[str, object]:
        if isinstance(item, dict):
            row = dict(item)
        elif hasattr(item, "to_dict"):
            row = dict(item.to_dict())
        else:
            row = dict(item)
        if row.get("tenant_id") != tenant_id:
            raise ValueError("migration batch contains another tenant")
        required = {
            "id",
            "vector",
            "tenant_id",
            "knowledge_base_id",
            "document_id",
            "chunk_id",
        }
        missing = required.difference(row)
        if missing:
            raise ValueError(
                "migration row is missing fields: " + ", ".join(sorted(missing))
            )
        row["document_version"] = int(row.get("document_version", 1))
        row["is_active"] = bool(row.get("is_active", True))
        return row
