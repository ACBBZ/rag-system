from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from minio import Minio
from pymilvus import MilvusClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rag.config import Settings
from rag.storage.database import get_async_engine, get_sessionmaker


_current_runtime: "RuntimeResources | None" = None


@dataclass
class RuntimeResources:
    engine: AsyncEngine | object
    sessionmaker: async_sessionmaker[AsyncSession] | object
    http_client: httpx.AsyncClient | object
    milvus_client: MilvusClient | object
    minio_client: Minio | object


def create_runtime(settings: Settings) -> RuntimeResources:
    global _current_runtime
    engine = get_async_engine(settings)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.model_connect_timeout_seconds,
            read=settings.model_read_timeout_seconds,
            write=settings.model_write_timeout_seconds,
            pool=settings.model_pool_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.model_max_connections,
            max_keepalive_connections=settings.model_max_keepalive_connections,
        ),
    )
    _current_runtime = RuntimeResources(
        engine=engine,
        sessionmaker=get_sessionmaker(engine),
        http_client=http_client,
        milvus_client=MilvusClient(uri=settings.milvus_uri),
        minio_client=Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        ),
    )
    return _current_runtime


def get_current_runtime() -> RuntimeResources | None:
    return _current_runtime


async def close_runtime(runtime: RuntimeResources) -> None:
    global _current_runtime
    if isinstance(runtime.http_client, httpx.AsyncClient):
        await runtime.http_client.aclose()
    if isinstance(runtime.engine, AsyncEngine):
        await runtime.engine.dispose()
    close = getattr(runtime.milvus_client, "close", None)
    if callable(close):
        await asyncio.to_thread(close)
    if _current_runtime is runtime:
        _current_runtime = None


async def check_runtime_readiness(runtime: RuntimeResources, bucket: str) -> dict[str, bool]:
    checks = {"postgres": False, "minio": False, "milvus": False}
    try:
        if isinstance(runtime.engine, AsyncEngine):
            async with runtime.engine.connect() as connection:
                await connection.execute(text("select 1"))
            checks["postgres"] = True
    except Exception:
        pass
    try:
        bucket_exists = getattr(runtime.minio_client, "bucket_exists")
        checks["minio"] = bool(await asyncio.to_thread(bucket_exists, bucket))
    except Exception:
        pass
    try:
        list_collections = getattr(runtime.milvus_client, "list_collections")
        await asyncio.to_thread(list_collections)
        checks["milvus"] = True
    except Exception:
        pass
    return checks
