from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://stajor1:stajor1*-@192.168.40.140:5432/stajor",
)

# Test override: set to sqlite+aiosqlite:///:memory: for unit tests
_TEST_DATABASE_URL: str | None = None


def _get_engine_url() -> str:
    return _TEST_DATABASE_URL or DATABASE_URL


engine = create_async_engine(_get_engine_url(), echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def set_test_database_url(url: str) -> None:
    global _TEST_DATABASE_URL, engine, AsyncSessionLocal
    _TEST_DATABASE_URL = url
    engine = create_async_engine(url, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
