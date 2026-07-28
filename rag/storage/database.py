from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from rag.config import Settings


class Base(DeclarativeBase):
    pass


def get_async_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.postgres_dsn, pool_pre_ping=True)


def get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
