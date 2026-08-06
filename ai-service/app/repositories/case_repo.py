from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import CaseModel


class CaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, case: CaseModel) -> CaseModel:
        case.created_at = datetime.utcnow()
        self._session.add(case)
        await self._session.commit()
        await self._session.refresh(case)
        return case

    async def find_by_pattern(self, pattern: str) -> Sequence[CaseModel]:
        stmt = select(CaseModel).where(CaseModel.pattern == pattern).order_by(CaseModel.last_seen.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_id(self, case_id: uuid.UUID) -> CaseModel | None:
        stmt = select(CaseModel).where(CaseModel.id == case_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_trending(self, limit: int = 20) -> Sequence[CaseModel]:
        stmt = (
            select(CaseModel)
            .where(CaseModel.trend_direction == "rising")
            .order_by(CaseModel.occurrence_count.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_new_patterns(self, min_count: int = 3) -> Sequence[CaseModel]:
        stmt = (
            select(CaseModel)
            .where(CaseModel.occurrence_count >= min_count)
            .order_by(CaseModel.created_at.desc())
            .limit(50)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def upsert(self, pattern: str, hotel: str | None, aof_ids: list[uuid.UUID]) -> CaseModel:
        existing = await self.find_by_pattern(pattern)
        if existing:
            case = existing[0]
            case.occurrence_count += 1
            case.last_seen = datetime.utcnow()
            existing_ids = set(case.aof_ids or [])
            existing_ids.update(aof_ids)
            case.aof_ids = list(existing_ids)
            await self._session.commit()
            await self._session.refresh(case)
            return case
        case = CaseModel(
            pattern=pattern,
            hotel=hotel,
            aof_ids=aof_ids,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            occurrence_count=1,
        )
        return await self.create(case)

    async def count(self) -> int:
        stmt = select(func.count(CaseModel.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0
