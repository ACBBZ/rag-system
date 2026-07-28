import re

from pymilvus import MilvusClient

from rag.config import Settings
from rag.schemas import RetrievedChunk, TenantContext

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _safe_filter_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


class MilvusVectorStore:
    def __init__(self, settings: Settings) -> None:
        self.collection = settings.milvus_collection
        self.client = MilvusClient(uri=settings.milvus_uri)

    def upsert_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        chunk_ids: list[str],
        vectors: list[list[float]],
    ) -> None:
        _safe_filter_id(tenant.tenant_id, "tenant_id")
        _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        _safe_filter_id(document_id, "document_id")
        rows = [
            {
                "id": chunk_id,
                "vector": vector,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "is_active": True,
            }
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection, data=rows)

    def search(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        tenant_id = _safe_filter_id(tenant.tenant_id, "tenant_id")
        kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        filter_expr = (
            f'tenant_id == "{tenant_id}" and '
            f'knowledge_base_id == "{kb_id}" and is_active == true'
        )
        results = self.client.search(
            collection_name=self.collection,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=["chunk_id", "document_id"],
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

    def delete_document(self, tenant_id: str, knowledge_base_id: str, document_id: str) -> None:
        safe_tenant_id = _safe_filter_id(tenant_id, "tenant_id")
        safe_kb_id = _safe_filter_id(knowledge_base_id, "knowledge_base_id")
        safe_document_id = _safe_filter_id(document_id, "document_id")
        self.client.delete(
            collection_name=self.collection,
            filter=(
                f'tenant_id == "{safe_tenant_id}" and '
                f'knowledge_base_id == "{safe_kb_id}" and '
                f'document_id == "{safe_document_id}"'
            ),
        )
