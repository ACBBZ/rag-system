from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config import Settings
from rag.errors import NotFoundError
from rag.storage.milvus_schema import (
    TENANT_VECTOR_SCHEMA_VERSION,
    build_collection_names,
    schema_fingerprint,
    vector_index_params,
    vector_search_params,
)


@dataclass(frozen=True)
class TenantVectorResource:
    id: str
    tenant_id: str
    logical_alias: str
    physical_collection: str
    schema_version: int
    embedding_model: str
    embedding_dimension: int
    metric_type: str
    index_type: str
    index_params: dict[str, object]
    search_params: dict[str, object]
    schema_fingerprint: str
    status: str
    last_error: str | None = None
    activated_at: datetime | None = None

    @classmethod
    def from_mapping(cls, row) -> "TenantVectorResource":
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            logical_alias=row["logical_alias"],
            physical_collection=row["physical_collection"],
            schema_version=int(row["schema_version"]),
            embedding_model=row["embedding_model"],
            embedding_dimension=int(row["embedding_dimension"]),
            metric_type=row["metric_type"],
            index_type=row["index_type"],
            index_params=dict(row["index_params"] or {}),
            search_params=dict(row["search_params"] or {}),
            schema_fingerprint=row["schema_fingerprint"],
            status=row["status"],
            last_error=row.get("last_error"),
            activated_at=row.get("activated_at"),
        )

    def to_summary(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "logical_alias": self.logical_alias,
            "physical_collection": self.physical_collection,
            "schema_version": self.schema_version,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "metric_type": self.metric_type,
            "index_type": self.index_type,
            "status": self.status,
            "last_error": self.last_error,
            "activated_at": self.activated_at,
        }


class VectorResourceRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def tenant_exists(self, tenant_id: str) -> bool:
        result = await self.session.execute(
            text("select 1 from tenants where id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        return result.first() is not None

    async def create_pending(self, tenant_id: str) -> TenantVectorResource:
        if not await self.tenant_exists(tenant_id):
            raise NotFoundError("tenant not found")

        expected_fingerprint = schema_fingerprint(self.settings)
        existing = await self.get(tenant_id)
        if existing is not None:
            if existing.schema_fingerprint != expected_fingerprint:
                raise ValueError(
                    "configured vector schema does not match the existing tenant resource"
                )
            return existing

        names = build_collection_names(
            tenant_id,
            self.settings.milvus_collection_prefix,
        )
        resource_id = f"vec_{uuid4().hex}"
        index_params = vector_index_params(self.settings)
        search_params = vector_search_params(self.settings)
        await self.session.execute(
            text(
                """
                insert into tenant_vector_resources (
                    id, tenant_id, provider, cluster_key, logical_alias,
                    physical_collection, schema_version, embedding_model,
                    embedding_dimension, metric_type, index_type, index_params,
                    search_params, schema_fingerprint, status
                ) values (
                    :id, :tenant_id, 'milvus', 'default', :logical_alias,
                    :physical_collection, :schema_version, :embedding_model,
                    :embedding_dimension, :metric_type, :index_type,
                    cast(:index_params as json), cast(:search_params as json),
                    :schema_fingerprint, 'pending'
                )
                """
            ),
            {
                "id": resource_id,
                "tenant_id": tenant_id,
                "logical_alias": names.alias,
                "physical_collection": names.physical,
                "schema_version": TENANT_VECTOR_SCHEMA_VERSION,
                "embedding_model": self.settings.embedding_model,
                "embedding_dimension": self.settings.milvus_vector_dimension,
                "metric_type": self.settings.milvus_metric_type.upper(),
                "index_type": self.settings.milvus_index_type.upper(),
                "index_params": json.dumps(index_params),
                "search_params": json.dumps(search_params),
                "schema_fingerprint": expected_fingerprint,
            },
        )
        created = await self.get(tenant_id)
        if created is None:
            raise RuntimeError("failed to create tenant vector resource")
        return created

    async def get(self, tenant_id: str) -> TenantVectorResource | None:
        result = await self.session.execute(
            text(
                """
                select * from tenant_vector_resources
                where tenant_id = :tenant_id
                limit 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        return TenantVectorResource.from_mapping(row) if row is not None else None

    async def get_ready(self, tenant_id: str) -> TenantVectorResource | None:
        result = await self.session.execute(
            text(
                """
                select * from tenant_vector_resources
                where tenant_id = :tenant_id and status = 'ready'
                limit 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        return TenantVectorResource.from_mapping(row) if row is not None else None

    async def mark_creating(self, resource_id: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_resources
                set status = 'creating', last_error = null, updated_at = now()
                where id = :id
                """
            ),
            {"id": resource_id},
        )

    async def mark_ready(self, resource_id: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_resources
                set status = 'ready', last_error = null,
                    activated_at = coalesce(activated_at, now()), updated_at = now()
                where id = :id
                """
            ),
            {"id": resource_id},
        )

    async def mark_failed(self, resource_id: str, error: str) -> None:
        await self.session.execute(
            text(
                """
                update tenant_vector_resources
                set status = 'failed', last_error = :error, updated_at = now()
                where id = :id
                """
            ),
            {"id": resource_id, "error": error[:4000]},
        )
