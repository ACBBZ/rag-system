from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    minio_endpoint: str = Field(alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="rag-system", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    milvus_uri: str = Field(alias="MILVUS_URI")
    milvus_collection_prefix: str = Field(default="rag", alias="MILVUS_COLLECTION_PREFIX")
    milvus_vector_dimension: int = Field(default=1024, ge=2, alias="MILVUS_VECTOR_DIMENSION")
    milvus_metric_type: str = Field(default="COSINE", alias="MILVUS_METRIC_TYPE")
    milvus_index_type: str = Field(default="HNSW", alias="MILVUS_INDEX_TYPE")
    milvus_index_m: int = Field(default=16, ge=2, alias="MILVUS_INDEX_M")
    milvus_index_ef_construction: int = Field(default=200, ge=8, alias="MILVUS_INDEX_EF_CONSTRUCTION")
    milvus_search_ef: int = Field(default=64, ge=1, alias="MILVUS_SEARCH_EF")

    api_key_pepper: str = Field(default="", alias="API_KEY_PEPPER")
    platform_api_key: str = Field(default="", alias="PLATFORM_API_KEY")

    embedding_url: str = Field(alias="EMBEDDING_URL")
    embedding_model: str = Field(alias="EMBEDDING_MODEL")
    embedding_api_key: str = Field(alias="EMBEDDING_API_KEY")
    rerank_url: str = Field(alias="RERANK_URL")
    rerank_model: str = Field(alias="RERANK_MODEL")
    rerank_api_key: str = Field(alias="RERANK_API_KEY")
    query_rewrite_url: str = Field(alias="QUERY_REWRITE_URL")
    query_rewrite_model: str = Field(alias="QUERY_REWRITE_MODEL")
    query_rewrite_api_key: str = Field(alias="QUERY_REWRITE_API_KEY")
    llm_url: str = Field(alias="LLM_URL")
    llm_model: str = Field(alias="LLM_MODEL")
    llm_api_key: str = Field(alias="LLM_API_KEY")
    ocr_url: str = Field(default="", alias="OCR_URL")
    ocr_model: str = Field(default="", alias="OCR_MODEL")
    ocr_api_key: str = Field(default="", alias="OCR_API_KEY")

    model_connect_timeout_seconds: float = Field(default=5.0, gt=0, alias="MODEL_CONNECT_TIMEOUT_SECONDS")
    model_read_timeout_seconds: float = Field(default=60.0, gt=0, alias="MODEL_READ_TIMEOUT_SECONDS")
    model_write_timeout_seconds: float = Field(default=30.0, gt=0, alias="MODEL_WRITE_TIMEOUT_SECONDS")
    model_pool_timeout_seconds: float = Field(default=5.0, gt=0, alias="MODEL_POOL_TIMEOUT_SECONDS")
    model_max_attempts: int = Field(default=3, ge=1, le=8, alias="MODEL_MAX_ATTEMPTS")
    model_retry_backoff_seconds: float = Field(default=0.2, ge=0, alias="MODEL_RETRY_BACKOFF_SECONDS")
    model_max_connections: int = Field(default=100, ge=1, alias="MODEL_MAX_CONNECTIONS")
    model_max_keepalive_connections: int = Field(default=20, ge=1, alias="MODEL_MAX_KEEPALIVE_CONNECTIONS")
    strict_embedding_dimension: bool = Field(default=False, alias="STRICT_EMBEDDING_DIMENSION")

    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1024, alias="MAX_UPLOAD_BYTES")
    max_pdf_pages: int = Field(default=1000, ge=1, alias="MAX_PDF_PAGES")
    max_image_pixels: int = Field(default=40_000_000, ge=1, alias="MAX_IMAGE_PIXELS")
    max_spreadsheet_rows: int = Field(default=100_000, ge=1, alias="MAX_SPREADSHEET_ROWS")
    ingestion_max_attempts: int = Field(default=3, ge=1, le=20, alias="INGESTION_MAX_ATTEMPTS")
    ingestion_stale_seconds: int = Field(default=900, ge=30, alias="INGESTION_STALE_SECONDS")

    chunk_target_tokens: int = Field(default=450, ge=32, alias="CHUNK_TARGET_TOKENS")
    chunk_max_tokens: int = Field(default=600, ge=64, alias="CHUNK_MAX_TOKENS")
    chunk_overlap_tokens: int = Field(default=60, ge=0, alias="CHUNK_OVERLAP_TOKENS")
    context_max_tokens: int = Field(default=6000, ge=128, alias="CONTEXT_MAX_TOKENS")

    default_query_rewrite_enabled: bool = Field(default=False, alias="DEFAULT_QUERY_REWRITE_ENABLED")
    default_vector_search_enabled: bool = Field(default=True, alias="DEFAULT_VECTOR_SEARCH_ENABLED")
    default_full_text_search_enabled: bool = Field(default=False, alias="DEFAULT_FULL_TEXT_SEARCH_ENABLED")
    default_hybrid_search_enabled: bool = Field(default=False, alias="DEFAULT_HYBRID_SEARCH_ENABLED")
    default_rerank_enabled: bool = Field(default=False, alias="DEFAULT_RERANK_ENABLED")
    default_agent_search_enabled: bool = Field(default=False, alias="DEFAULT_AGENT_SEARCH_ENABLED")
    default_vector_weight: float = Field(default=1.0, ge=0, alias="DEFAULT_VECTOR_WEIGHT")
    default_lexical_weight: float = Field(default=0.8, ge=0, alias="DEFAULT_LEXICAL_WEIGHT")
    default_rrf_k: int = Field(default=60, ge=1, alias="DEFAULT_RRF_K")
    default_rerank_candidate_k: int = Field(default=30, ge=1, alias="DEFAULT_RERANK_CANDIDATE_K")
    default_per_document_limit: int = Field(default=3, ge=1, alias="DEFAULT_PER_DOCUMENT_LIMIT")
    default_score_threshold: float | None = Field(default=None, alias="DEFAULT_SCORE_THRESHOLD")

    @model_validator(mode="after")
    def validate_limits(self) -> "Settings":
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("CHUNK_TARGET_TOKENS cannot exceed CHUNK_MAX_TOKENS")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_MAX_TOKENS")
        if self.api_key_pepper and len(self.api_key_pepper) < 32:
            raise ValueError("API_KEY_PEPPER must contain at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
