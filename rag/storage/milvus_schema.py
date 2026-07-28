from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from pymilvus import DataType, MilvusClient

from rag.config import Settings

_SAFE_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


@dataclass(frozen=True)
class CollectionNames:
    alias: str
    physical: str


def build_collection_names(
    tenant_id: str,
    prefix: str,
    schema_version: int,
) -> CollectionNames:
    if not _SAFE_PREFIX.fullmatch(prefix):
        raise ValueError("invalid Milvus collection prefix")
    if schema_version < 1:
        raise ValueError("schema_version must be positive")
    digest = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:16]
    base = f"{prefix}_t_{digest}"
    return CollectionNames(
        alias=f"{base}_current",
        physical=f"{base}_v{schema_version}",
    )


def vector_index_params(settings: Settings) -> dict[str, object]:
    if settings.milvus_index_type.upper() == "HNSW":
        return {
            "M": settings.milvus_index_m,
            "efConstruction": settings.milvus_index_ef_construction,
        }
    return {}


def schema_fingerprint(settings: Settings) -> str:
    payload = {
        "schema_version": settings.milvus_schema_version,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.milvus_vector_dimension,
        "metric_type": settings.milvus_metric_type.upper(),
        "index_type": settings.milvus_index_type.upper(),
        "index_params": vector_index_params(settings),
        "fields": [
            ["id", "VARCHAR", 256],
            ["vector", "FLOAT_VECTOR", settings.milvus_vector_dimension],
            ["tenant_id", "VARCHAR", 128],
            ["knowledge_base_id", "VARCHAR", 128],
            ["document_id", "VARCHAR", 128],
            ["chunk_id", "VARCHAR", 256],
            ["document_version", "INT64", None],
            ["is_active", "BOOL", None],
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_collection_schema(dimension: int):
    if dimension < 2:
        raise ValueError("embedding dimension must be at least 2")
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(
        field_name="id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=256,
    )
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)
    schema.add_field(field_name="tenant_id", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(
        field_name="knowledge_base_id",
        datatype=DataType.VARCHAR,
        max_length=128,
    )
    schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="document_version", datatype=DataType.INT64)
    schema.add_field(field_name="is_active", datatype=DataType.BOOL)
    return schema


def build_index_params(client: MilvusClient, settings: Settings):
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_name="vector_index",
        index_type=settings.milvus_index_type.upper(),
        metric_type=settings.milvus_metric_type.upper(),
        params=vector_index_params(settings),
    )
    return index_params


def described_vector_dimension(description: dict[str, object]) -> int | None:
    for field in description.get("fields", []):
        if isinstance(field, dict) and field.get("name") == "vector":
            params = field.get("params") or {}
            if isinstance(params, dict) and "dim" in params:
                return int(params["dim"])
    return None
