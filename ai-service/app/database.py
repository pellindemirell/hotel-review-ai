from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Bağlantı bilgisi yalnızca ortam değişkeninden gelir. Önceden buraya üretim
# sunucusunun IP'si ve şifresi varsayılan olarak gömülüydü; hem sırrı git'e
# taşıyordu hem de yanlış yapılandırma sessizce üretim veritabanına bağlanıyordu.
DATABASE_URL = os.getenv("DATABASE_URL")

# Test override: unit testler için sqlite+aiosqlite:///:memory:
_TEST_DATABASE_URL: str | None = None

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine_url() -> str:
    url = _TEST_DATABASE_URL or DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL tanımlı değil. .env dosyanıza ekleyin "
            "(örnek için .env.example dosyasına bakın)."
        )
    return url


# Engine tembel (lazy) oluşturulur: modül import edildiğinde veritabanı sürücüsü
# yüklenmez. Aksi hâlde `from app.database import Base` yapan her modül -- ve
# tests/conftest.py -- DATABASE_URL/asyncpg olmadan import aşamasında çöküyordu.
def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            _get_engine_url(), echo=False, pool_size=5, max_overflow=10
        )
        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def set_test_database_url(url: str) -> None:
    global _TEST_DATABASE_URL, _engine, _session_factory
    _TEST_DATABASE_URL = url
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
