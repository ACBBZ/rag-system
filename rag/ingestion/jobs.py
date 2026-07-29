from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from rag.schemas import TenantContext


class IngestionJobStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    VALIDATING = "validating"
    ACTIVATING = "activating"
    COMPLETED = "completed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


class ClaimedIngestionJob(BaseModel):
    job_id: str
    tenant_id: str
    knowledge_base_id: str
    document_id: str
    document_version: int
    raw_object_key: str
    filename: str
    metadata: dict[str, object] = Field(default_factory=dict)
    tenant_context: TenantContext | None = None
    attempt: int = 1
    max_attempts: int = 3
