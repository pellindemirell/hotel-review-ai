from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")

_engine = None
_async_session_maker = None
_override_url = None


def _get_engine_url() -> str:
    return _override_url or DATABASE_URL


def _ensure_engine() -> None:
    global _engine, _async_session_maker
    if _engine is not None:
        return
    url = _get_engine_url()
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    _engine = create_async_engine(url, echo=False, pool_size=5, max_overflow=10)
    _async_session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    _ensure_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    _ensure_engine()
    async with _async_session_maker() as session:
        yield session


async def shutdown_db() -> None:
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None


def configure_database(url: str) -> None:
    global _override_url, _engine, _async_session_maker
    _override_url = url
    _engine = None
    _async_session_maker = None
