from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    tenant_id: str
    organization_id: str | None = None
    user_id: str
    knowledge_base_ids: list[str]
    roles: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)

    def can_access_knowledge_base(self, knowledge_base_id: str) -> bool:
        return knowledge_base_id in self.knowledge_base_ids

    def has_scope(self, scope: str) -> bool:
        return scope in self.allowed_scopes


class RetrievalOptions(BaseModel):
    query_rewrite: bool | None = None
    vector_search: bool | None = None
    full_text_search: bool | None = None
    hybrid_search: bool | None = None
    rerank: bool | None = None
    agent_search: bool | None = None
    top_k: int = Field(default=20, ge=1, le=100)
    final_k: int = Field(default=5, ge=1, le=50)


class RetrievalFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    retrieval_method: str
    source: dict[str, str | int | None]
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str | None = None
    source_uri: str | None = None
    page: int | None = None
    quote: str


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RetrievalSearchRequest(BaseModel):
    knowledge_base_id: str
    query: str = Field(min_length=1)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class RetrievalSearchResponse(BaseModel):
    query_id: str
    rewritten_query: str | None = None
    chunks: list[RetrievedChunk]
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage | None = None


class EmbedDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    status: str


class UpdateDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    version: int
    status: str


class PurgeDocumentResponse(BaseModel):
    document_id: str
    status: str

