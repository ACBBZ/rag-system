from __future__ import annotations

from dataclasses import replace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient
from rag.schemas import TenantContext, TenantVectorRoute
from rag.storage.milvus_collection_manager import MilvusCollectionManager
from rag.storage.milvus_schema import (
    TENANT_VECTOR_SCHEMA_VERSION,
    build_collection_schema,
    schema_fingerprint,
)
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.vector_resources import TenantVectorResource


class MilvusV2Migrator:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        client,
        model_client: ModelEndpointClient,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client = client
        self.model_client = model_client

    async def migrate(
        self,
        resource: TenantVectorResource,
        batch_size: int = 64,
    ) -> str:
        if resource.schema_version >= TENANT_VECTOR_SCHEMA_VERSION:
            return resource.physical_collection
        new_physical = (
            resource.physical_collection.rsplit("_v", 1)[0]
            + f"_v{TENANT_VECTOR_SCHEMA_VERSION}"
        )
        target = replace(
            resource,
            physical_collection=new_physical,
            schema_version=TENANT_VECTOR_SCHEMA_VERSION,
            schema_fingerprint=schema_fingerprint(self.settings),
            status="creating",
        )
        manager = MilvusCollectionManager(self.client, self.settings)
        if not self.client.has_collection(collection_name=new_physical):
            schema = build_collection_schema(resource.embedding_dimension)
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="vector",
                index_name="vector_index",
                index_type=resource.index_type,
                metric_type=resource.metric_type,
                params=resource.index_params,
            )
            self.client.create_collection(
                collection_name=new_physical,
                schema=schema,
                index_params=index_params,
            )
        manager._validate_collection(target)
        result = await self.session.execute(
            text(
                """
                select id, knowledge_base_id, document_id, document_version,
                       text, metadata, language,
                       coalesce(page_start, page) as page_start
                from chunks
                where tenant_id = :tenant_id and is_active = true
                order by id
                """
            ),
            {"tenant_id": resource.tenant_id},
        )
        rows = list(result.mappings())
        route = TenantVectorRoute(
            collection_alias=new_physical,
            physical_collection=new_physical,
            schema_version=TENANT_VECTOR_SCHEMA_VERSION,
            embedding_model=resource.embedding_model,
            embedding_dimension=resource.embedding_dimension,
            metric_type=resource.metric_type,
            index_type=resource.index_type,
            search_params=resource.search_params,
        )
        tenant = TenantContext(
            tenant_id=resource.tenant_id,
            user_id="system",
            vector_route=route,
        )
        store = MilvusVectorStore(self.settings, client=self.client)
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            vectors = await self.model_client.embed(
                [row["text"] for row in batch]
            )
            grouped: dict[tuple[str, str, int], list[tuple[object, list[float]]]] = {}
            for row, vector in zip(batch, vectors, strict=True):
                key = (
                    row["knowledge_base_id"],
                    row["document_id"],
                    int(row["document_version"]),
                )
                grouped.setdefault(key, []).append((row, vector))
            for (kb_id, document_id, version), items in grouped.items():
                await store.upsert_chunks(
                    tenant,
                    kb_id,
                    document_id,
                    [item[0]["id"] for item in items],
                    [item[1] for item in items],
                    document_version=version,
                    metadata=[dict(item[0]["metadata"] or {}) for item in items],
                    languages=[item[0]["language"] or "und" for item in items],
                    pages=[item[0]["page_start"] for item in items],
                    is_active=True,
                )
        stats = self.client.get_collection_stats(
            collection_name=new_physical
        )
        if int(stats.get("row_count") or 0) < len(rows):
            raise RuntimeError("Milvus V2 migration row-count validation failed")
        self.client.alter_alias(
            collection_name=new_physical,
            alias=resource.logical_alias,
        )
        await self.session.execute(
            text(
                """
                update tenant_vector_resources
                set previous_physical_collection = physical_collection,
                    physical_collection = :physical_collection,
                    schema_version = :schema_version,
                    schema_fingerprint = :fingerprint,
                    status = 'ready', activated_at = now(), updated_at = now()
                where id = :id
                """
            ),
            {
                "id": resource.id,
                "physical_collection": new_physical,
                "schema_version": TENANT_VECTOR_SCHEMA_VERSION,
                "fingerprint": schema_fingerprint(self.settings),
            },
        )
        return new_physical
