from __future__ import annotations

import asyncio
import json
import re

from pymilvus import MilvusClient

from rag.config import Settings
from rag.schemas import RetrievedChunk, TenantContext, TenantVectorRoute
from rag.storage.tenant_collection_resolver import TenantCollectionResolver

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_COLLECTION = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,254}$")
_SAFE_METADATA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _safe_filter_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _safe_collection_name(value: str) -> str:
    if not _SAFE_COLLECTION.fullmatch(value):
        raise ValueError("invalid Milvus collection name")
    return value


def compile_milvus_metadata_filter(
    metadata: dict[str, str | int | float | bool],
) -> str:
    parts: list[str] = []
    for key in sorted(metadata):
        if not _SAFE_METADATA_KEY.fullmatch(key):
            raise ValueError("invalid metadata filter key")
        value = metadata[key]
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("metadata filters only support scalar values")
        encoded = json.dumps(value, ensure_ascii=False)
        parts.append(f'metadata["{key}"] == {encoded}')
    return " and ".join(parts)


class MilvusVectorStore:
    def __init__(
        self,
        settings: Settings,
        *,
        client: MilvusClient | None = None,
        resolver: TenantCollectionResolver | None = None,
    ) -> None:
        self.client = client or MilvusClient(uri=settings.milvus_uri)
        self.resolver = resolver or TenantCollectionResolver()

    def _resolve(self, tenant: TenantContext) -> TenantVectorRoute:
        route = self.resolver.resolve(tenant)
        _safe_collection_name(route.collection_alias)
        _safe_collection_name(route.physical_collection)
        return route

    async def upsert_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        chunk_ids: list[str],
        vectors: list[list[float]],
        *,
        document_version: int = 1,
        metadata: list[dict[str, object]] | None = None,
        languages: list[str] | None = None,
        pages: list[int | None] | None = None,
        is_active: bool = True,
    ) -> None:
        route = self._resolve(tenant)
        _safe_filter_id(tenant.tenant_id, "tenant_id")
        _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        _safe_filter_id(document_id, "document_id")
        if len(chunk_ids) != len(vectors):
            raise ValueError("chunk and vector counts must match")
        if any(
            len(vector) != route.embedding_dimension
            for vector in vectors
        ):
            raise ValueError(
                "embedding dimension does not match tenant collection"
            )
        active_metadata = metadata or [{} for _ in chunk_ids]
        active_languages = languages or ["und" for _ in chunk_ids]
        active_pages = pages or [None for _ in chunk_ids]
        rows = []
        for chunk_id, vector, chunk_metadata, language, page in zip(
            chunk_ids,
            vectors,
            active_metadata,
            active_languages,
            active_pages,
            strict=True,
        ):
            row = {
                "id": chunk_id,
                "vector": vector,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "document_version": document_version,
                "is_active": is_active,
            }
            if route.schema_version >= 2:
                row.update(
                    {
                        "language": language,
                        "page_start": page,
                        "page_end": page,
                        "metadata": chunk_metadata,
                    }
                )
            rows.append(row)
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=route.collection_alias,
            data=rows,
        )

    @staticmethod
    def _score(distance: float, metric_type: str) -> float:
        if metric_type.upper() == "L2":
            return 1.0 / (1.0 + max(0.0, distance))
        return distance

    async def search(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        query_vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list[RetrievedChunk]:
        route = self._resolve(tenant)
        tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        if len(query_vector) != route.embedding_dimension:
            raise ValueError(
                "embedding dimension does not match tenant collection"
            )
        filter_parts = [
            f'tenant_id == "{tenant_id}"',
            f'knowledge_base_id == "{kb_id}"',
            "is_active == true",
        ]
        if document_ids:
            safe_ids = [
                _safe_filter_id(value, "document_id")
                for value in document_ids
            ]
            values = ", ".join(json.dumps(value) for value in safe_ids)
            filter_parts.append(f"document_id in [{values}]")
        if metadata and route.schema_version >= 2:
            filter_parts.append(compile_milvus_metadata_filter(metadata))
        params = dict(route.search_params)
        if route.index_type.upper() == "HNSW":
            params["ef"] = max(int(params.get("ef", top_k)), top_k)
        results = await asyncio.to_thread(
            self.client.search,
            collection_name=route.collection_alias,
            data=[query_vector],
            limit=top_k,
            filter=" and ".join(filter_parts),
            output_fields=["chunk_id", "document_id"],
            search_params={
                "metric_type": route.metric_type.upper(),
                "params": params,
            },
        )
        chunks: list[RetrievedChunk] = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            distance = float(hit["distance"])
            score = self._score(distance, route.metric_type)
            chunks.append(
                RetrievedChunk(
                    chunk_id=entity["chunk_id"],
                    document_id=entity["document_id"],
                    text="",
                    score=score,
                    final_score_type="vector_similarity",
                    retrieval_method="vector",
                    retrieval_methods=["vector"],
                    scores={
                        "vector_distance": distance,
                        "vector_similarity": score,
                    },
                    source={},
                    metadata={},
                )
            )
        return chunks

    async def activate_document_version(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        version: int,
    ) -> None:
        route = self._resolve(tenant)
        tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        doc_id = _safe_filter_id(document_id, "document_id")
        filter_expr = (
            f'tenant_id == "{tenant_id}" and '
            f'knowledge_base_id == "{kb_id}" and '
            f'document_id == "{doc_id}" and '
            f'document_version != {int(version)}'
        )
        await asyncio.to_thread(
            self.client.delete,
            collection_name=route.collection_alias,
            filter=filter_expr,
        )

    async def delete_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        route = self._resolve(tenant)
        tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        doc_id = _safe_filter_id(document_id, "document_id")
        filter_expr = (
            f'tenant_id == "{tenant_id}" and '
            f'knowledge_base_id == "{kb_id}" and '
            f'document_id == "{doc_id}"'
        )
        await asyncio.to_thread(
            self.client.delete,
            collection_name=route.collection_alias,
            filter=filter_expr,
        )
