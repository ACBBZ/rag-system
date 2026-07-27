from functools import lru_cache

from pydantic import Field
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
    milvus_collection: str = Field(default="rag_chunks", alias="MILVUS_COLLECTION")

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

    default_query_rewrite_enabled: bool = Field(default=False, alias="DEFAULT_QUERY_REWRITE_ENABLED")
    default_vector_search_enabled: bool = Field(default=True, alias="DEFAULT_VECTOR_SEARCH_ENABLED")
    default_full_text_search_enabled: bool = Field(
        default=False, alias="DEFAULT_FULL_TEXT_SEARCH_ENABLED"
    )
    default_hybrid_search_enabled: bool = Field(default=False, alias="DEFAULT_HYBRID_SEARCH_ENABLED")
    default_rerank_enabled: bool = Field(default=False, alias="DEFAULT_RERANK_ENABLED")
    default_agent_search_enabled: bool = Field(default=False, alias="DEFAULT_AGENT_SEARCH_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
