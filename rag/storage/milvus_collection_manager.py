from __future__ import annotations

from pymilvus import MilvusClient

from rag.config import Settings
from rag.storage.milvus_schema import (
    build_collection_schema,
    described_vector_dimension,
)
from rag.storage.vector_resources import TenantVectorResource

_V1_FIELDS = {
    "id",
    "vector",
    "tenant_id",
    "knowledge_base_id",
    "document_id",
    "chunk_id",
    "document_version",
    "is_active",
}
_V2_FIELDS = _V1_FIELDS | {"language", "page_start", "page_end", "metadata"}


class MilvusCollectionManager:
    def __init__(self, client: MilvusClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def ensure_collection(self, resource: TenantVectorResource) -> None:
        if self.client.has_collection(
            collection_name=resource.physical_collection
        ):
            self._validate_collection(resource)
        else:
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
                collection_name=resource.physical_collection,
                schema=schema,
                index_params=index_params,
            )
            self._validate_collection(resource)
        self._ensure_alias(resource)

    def _validate_collection(self, resource: TenantVectorResource) -> None:
        description = self.client.describe_collection(
            collection_name=resource.physical_collection
        )
        dimension = described_vector_dimension(description)
        if dimension != resource.embedding_dimension:
            raise ValueError(
                "existing Milvus collection embedding dimension "
                "does not match resource"
            )
        field_names = {
            field.get("name")
            for field in description.get("fields", [])
            if isinstance(field, dict)
        }
        required = _V2_FIELDS if resource.schema_version >= 2 else _V1_FIELDS
        missing = required.difference(field_names)
        if missing:
            raise ValueError(
                "existing Milvus collection schema is missing fields: "
                + ", ".join(sorted(missing))
            )
        if description.get("enable_dynamic_field") is True:
            raise ValueError("existing Milvus collection must disable dynamic fields")

    def _ensure_alias(self, resource: TenantVectorResource) -> None:
        try:
            alias_description = self.client.describe_alias(
                alias=resource.logical_alias
            )
        except Exception:
            self.client.create_alias(
                collection_name=resource.physical_collection,
                alias=resource.logical_alias,
            )
            return
        current = alias_description.get("collection_name") or alias_description.get(
            "collection"
        )
        if current != resource.physical_collection:
            raise ValueError("tenant alias points to an unexpected collection")

    def drop_resource(self, resource: TenantVectorResource) -> None:
        try:
            alias_description = self.client.describe_alias(
                alias=resource.logical_alias
            )
        except Exception:
            alias_description = None
        if alias_description is not None:
            current = alias_description.get(
                "collection_name"
            ) or alias_description.get("collection")
            if current != resource.physical_collection:
                raise ValueError("tenant alias points to an unexpected collection")
            self.client.drop_alias(alias=resource.logical_alias)
        if self.client.has_collection(
            collection_name=resource.physical_collection
        ):
            self.client.drop_collection(
                collection_name=resource.physical_collection
            )
