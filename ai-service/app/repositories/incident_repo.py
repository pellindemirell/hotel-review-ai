from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import IncidentModel


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, incident: IncidentModel) -> IncidentModel:
        incident.created_at = datetime.utcnow()
        self._session.add(incident)
        await self._session.commit()
        await self._session.refresh(incident)
        return incident

    async def find_by_failure_type(self, failure_type: str, limit: int = 50) -> Sequence[IncidentModel]:
        stmt = (
            select(IncidentModel)
            .where(IncidentModel.failure_type == failure_type)
            .order_by(IncidentModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_open(self) -> Sequence[IncidentModel]:
        stmt = select(IncidentModel).where(IncidentModel.is_open == True).order_by(IncidentModel.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_id(self, incident_id: uuid.UUID) -> IncidentModel | None:
        stmt = select(IncidentModel).where(IncidentModel.id == incident_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def close(self, incident_id: uuid.UUID) -> IncidentModel | None:
        incident = await self.find_by_id(incident_id)
        if incident:
            incident.is_open = False
            incident.ended_at = datetime.utcnow()
            await self._session.commit()
            await self._session.refresh(incident)
        return incident

    async def count_open(self) -> int:
        stmt = select(func.count(IncidentModel.id)).where(IncidentModel.is_open == True)
        result = await self._session.execute(stmt)
        return result.scalar() or 0
