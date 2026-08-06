from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import TrendModel


class TrendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, failure_key: str, trend_date: date, count: int = 1) -> TrendModel:
        stmt = select(TrendModel).where(
            and_(TrendModel.failure_key == failure_key, TrendModel.date == trend_date)
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.count = count
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        trend = TrendModel(
            failure_key=failure_key,
            date=trend_date,
            count=count,
        )
        self._session.add(trend)
        await self._session.commit()
        await self._session.refresh(trend)
        return trend

    async def find_by_key(self, failure_key: str, limit: int = 90) -> Sequence[TrendModel]:
        stmt = (
            select(TrendModel)
            .where(TrendModel.failure_key == failure_key)
            .order_by(TrendModel.date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_anomalies(self, limit: int = 50) -> Sequence[TrendModel]:
        stmt = (
            select(TrendModel)
            .where(TrendModel.is_anomaly == True)
            .order_by(TrendModel.date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_rising_keys(self, min_z: float = 2.0) -> Sequence[str]:
        stmt = (
            select(TrendModel.failure_key)
            .where(TrendModel.z_score >= min_z)
            .distinct()
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def mark_anomaly(self, trend_id: uuid.UUID, z_score: float) -> TrendModel | None:
        stmt = select(TrendModel).where(TrendModel.id == trend_id)
        result = await self._session.execute(stmt)
        trend = result.scalar_one_or_none()
        if trend:
            trend.z_score = z_score
            trend.is_anomaly = abs(z_score) > 2.0
            await self._session.commit()
            await self._session.refresh(trend)
        return trend
