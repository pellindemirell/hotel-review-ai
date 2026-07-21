from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import AOFModel


class AOFRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(self, aofs: list[AOFModel]) -> list[AOFModel]:
        now = datetime.utcnow()
        for aof in aofs:
            aof.created_at = now
            self._session.add(aof)
        await self._session.commit()
        return aofs

    async def find_by_review(self, review_id: str) -> Sequence[AOFModel]:
        stmt = select(AOFModel).where(AOFModel.review_id == review_id).order_by(AOFModel.chain_position)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_fact_type(self, fact_type: str, limit: int = 100) -> Sequence[AOFModel]:
        stmt = select(AOFModel).where(AOFModel.fact_type == fact_type).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_department(self, department: str, limit: int = 100) -> Sequence[AOFModel]:
        stmt = select(AOFModel).where(AOFModel.department == department).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_id(self, aof_id: uuid.UUID) -> AOFModel | None:
        stmt = select(AOFModel).where(AOFModel.id == aof_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count(self) -> int:
        stmt = select(func.count(AOFModel.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def delete_by_review(self, review_id: str) -> None:
        stmt = select(AOFModel).where(AOFModel.review_id == review_id)
        result = await self._session.execute(stmt)
        for aof in result.scalars().all():
            await self._session.delete(aof)
        await self._session.commit()
