from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TenantVectorRoute(BaseModel):
    collection_alias: str
    physical_collection: str
    embedding_model: str
    embedding_dimension: int
    metric_type: str
    index_type: str
    search_params: dict[str, object] = Field(default_factory=dict)
    schema_version: int = 1


class TenantContext(BaseModel):
    tenant_id: str
    organization_id: str | None = None
    user_id: str
    api_key_id: str | None = None
    tenant_role: str = "member"
    direct_permissions: list[str] = Field(default_factory=list)
    scope_limit: list[str] | None = None
    knowledge_base_limit: list[str] | None = None
    knowledge_base_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)
    vector_route: TenantVectorRoute | None = None

    def can_access_knowledge_base(self, knowledge_base_id: str) -> bool:
        if self.knowledge_base_limit is not None:
            return knowledge_base_id in self.knowledge_base_limit
        if self.knowledge_base_ids:
            return knowledge_base_id in self.knowledge_base_ids
        return True

    def has_scope(self, scope: str) -> bool:
        limits = (
            self.scope_limit
            if self.scope_limit is not None
            else self.allowed_scopes
        )
        return scope in limits if limits else False


class TenantSummary(BaseModel):
    id: str
    slug: str
    name: str
    status: str


class UserSummary(BaseModel):
    id: str
    tenant_id: str
    email: str
    display_name: str | None = None
    status: str
    role: str


class ApiKeyCreated(BaseModel):
    id: str
    prefix: str
    api_key: str
    expires_at: datetime | None = None


class VectorResourceSummary(BaseModel):
    id: str
    tenant_id: str
    logical_alias: str
    physical_collection: str
    schema_version: int
    embedding_model: str
    embedding_dimension: int
    metric_type: str
    index_type: str
    status: str
    last_error: str | None = None
    activated_at: datetime | None = None


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    owner_email: str = Field(min_length=3, max_length=320)
    owner_display_name: str | None = Field(default=None, max_length=200)
    default_knowledge_base_name: str | None = Field(
        default="Default",
        max_length=200,
    )


class CreateTenantResponse(BaseModel):
    tenant: TenantSummary
    owner: UserSummary
    knowledge_base_id: str | None = None
    api_key: ApiKeyCreated
    vector_resource: VectorResourceSummary | None = None


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    role: str = "member"


class UpdateUserRoleRequest(BaseModel):
    role: str


class PermissionGrantRequest(BaseModel):
    permission: str
    expires_at: datetime | None = None


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scope_limit: list[str] | None = None
    knowledge_base_limit: list[str] | None = None
    expires_at: datetime | None = None


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseSummary(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    status: str
    role: str | None = None


class KnowledgeBaseMemberRequest(BaseModel):
    role: str


class RetrievalOptions(BaseModel):
    retrieval_mode: Literal["vector", "full_text", "hybrid", "auto"] | None = None
    query_rewrite: bool | None = None
    vector_search: bool | None = None
    full_text_search: bool | None = None
    hybrid_search: bool | None = None
    rerank: bool | None = None
    agent_search: bool | None = None
    top_k: int = Field(default=20, ge=1, le=500)
    final_k: int = Field(default=5, ge=1, le=100)
    vector_weight: float | None = Field(default=None, ge=0)
    lexical_weight: float | None = Field(default=None, ge=0)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    rerank_candidate_k: int | None = Field(default=None, ge=1, le=500)
    per_document_limit: int | None = Field(default=None, ge=1, le=100)
    score_threshold: float | None = None
    include_diagnostics: bool = False
    allow_partial_results: bool = False


class RetrievalFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    final_score_type: str | None = None
    retrieval_method: str
    retrieval_methods: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    source: dict[str, str | int | None]
    metadata: dict[str, object] = Field(default_factory=dict)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str | None = None
    source_uri: str | None = None
    page: int | None = None
    quote: str


class GeneratedAnswer(BaseModel):
    answer: str | None
    cited_chunk_ids: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RetrievalSearchRequest(BaseModel):
    knowledge_base_id: str
    query: str = Field(min_length=1, max_length=20_000)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class RetrievalSearchResponse(BaseModel):
    query_id: str
    trace_id: str | None = None
    rewritten_query: str | None = None
    effective_options: dict[str, object] | None = None
    chunks: list[RetrievedChunk]
    answer: str | None = None
    answer_status: Literal[
        "not_requested",
        "answered",
        "insufficient_context",
        "conflicting_context",
        "generation_failed",
    ] = "not_requested"
    abstention_reason: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage | None = None
    timings: dict[str, float] = Field(default_factory=dict)
    degraded: bool = False
    degraded_components: list[str] = Field(default_factory=list)


class EmbedDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    version: int = 1
    status: str


class UpdateDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    version: int
    status: str


class PurgeDocumentResponse(BaseModel):
    document_id: str
    status: str


class IngestionJobResponse(BaseModel):
    job_id: str
    document_id: str | None = None
    document_version: int | None = None
    status: str
    stage: str | None = None
    progress: float = 0.0
    attempt: int = 0
    max_attempts: int = 3
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
