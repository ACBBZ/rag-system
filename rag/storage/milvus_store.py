import re

from pymilvus import MilvusClient

from rag.config import Settings
from rag.schemas import RetrievedChunk, TenantContext, TenantVectorRoute
from rag.storage.tenant_collection_resolver import TenantCollectionResolver

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_COLLECTION = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,254}$")


def _safe_filter_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _safe_collection_name(value: str) -> str:
    if not _SAFE_COLLECTION.fullmatch(value):
        raise ValueError("invalid Milvus collection name")
    return value


class MilvusVectorStore:
    def __init__(
        self,
        settings: Settings,
        *,
        client: MilvusClient | None = None,
        resolver: TenantCollectionResolver | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or MilvusClient(uri=settings.milvus_uri)
        self.resolver = resolver or TenantCollectionResolver(
            settings.legacy_milvus_collection
        )

    def _resolve(self, tenant: TenantContext) -> TenantVectorRoute:
        route = self.resolver.resolve(tenant)
        _safe_collection_name(route.collection_name)
        return route

    async def upsert_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        chunk_ids: list[str],
        vectors: list[list[float]],
    ) -> None:
        route = self._resolve(tenant)
        _safe_filter_id(tenant.tenant_id, "tenant_id")
        _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        _safe_filter_id(document_id, "document_id")
        if route.embedding_dimension > 0:
            invalid = [len(vector) for vector in vectors if len(vector) != route.embedding_dimension]
            if invalid:
                raise ValueError("embedding dimension does not match tenant collection")
        rows = []
        for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
            row = {
                "id": chunk_id,
                "vector": vector,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "is_active": True,
            }
            if route.mode == "tenant_collection":
                row["document_version"] = 1
            rows.append(row)
        self.client.upsert(collection_name=route.collection_name, data=rows)

    async def search(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        route = self._resolve(tenant)
        tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        if route.embedding_dimension > 0 and len(query_vector) != route.embedding_dimension:
            raise ValueError("embedding dimension does not match tenant collection")
        filter_expr = (
            f'tenant_id == "{tenant_id}" and '
            f'knowledge_base_id == "{kb_id}" and is_active == true'
        )
        search_params: dict[str, object] = {
            "metric_type": self.settings.milvus_metric_type.upper(),
            "params": {},
        }
        if self.settings.milvus_index_type.upper() == "HNSW":
            search_params["params"] = {
                "ef": max(self.settings.milvus_search_ef, top_k)
            }
        results = self.client.search(
            collection_name=route.collection_name,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=["chunk_id", "document_id"],
            search_params=search_params,
        )
        chunks: list[RetrievedChunk] = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            chunks.append(
                RetrievedChunk(
                    chunk_id=entity["chunk_id"],
                    document_id=entity["document_id"],
                    text="",
                    score=float(hit["distance"]),
                    retrieval_method="vector",
                    source={},
                    metadata={},
                )
            )
        return chunks

    async def delete_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        route = self._resolve(tenant)
        safe_tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        safe_kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        safe_document_id = _safe_filter_id(document_id, "document_id")
        self.client.delete(
            collection_name=route.collection_name,
            filter=(
                f'tenant_id == "{safe_tenant_id}" and '
                f'knowledge_base_id == "{safe_kb_id}" and '
                f'document_id == "{safe_document_id}"'
            ),
        )
