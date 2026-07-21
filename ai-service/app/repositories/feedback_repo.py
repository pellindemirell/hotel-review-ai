from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import FeedbackModel


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, feedback: FeedbackModel) -> FeedbackModel:
        feedback.created_at = datetime.utcnow()
        self._session.add(feedback)
        await self._session.commit()
        await self._session.refresh(feedback)
        return feedback

    async def find_by_aof(self, aof_id: uuid.UUID) -> Sequence[FeedbackModel]:
        stmt = select(FeedbackModel).where(FeedbackModel.aof_id == aof_id).order_by(FeedbackModel.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        stmt = select(func.count(FeedbackModel.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_disagreements(self, limit: int = 50) -> Sequence[FeedbackModel]:
        stmt = (
            select(FeedbackModel)
            .where(FeedbackModel.predicted_fact_type != FeedbackModel.corrected_fact_type)
            .order_by(FeedbackModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
