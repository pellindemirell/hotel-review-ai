from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Real, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AOFModel(Base):
    __tablename__ = "aofs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    clause: Mapped[str] = mapped_column(Text, nullable=False)
    fact_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    process: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Real, default=0.0)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    chain_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clause_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    journey_phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    sop_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    operational_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    financial_impact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recovery_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependency_chain: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    learning_signal: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Text, default=datetime.utcnow)  # will store isoformat


class CaseModel(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    hotel: Mapped[str | None] = mapped_column(Text, nullable=True)
    aof_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    first_seen: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    trend_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=datetime.utcnow)


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    failure_type: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    aof_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(Text, default=datetime.utcnow)


class TrendModel(Base):
    __tablename__ = "trends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    failure_key: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)
    z_score: Mapped[float | None] = mapped_column(Real, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(Text, default=datetime.utcnow)


class FeedbackModel(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aof_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("aofs.id"), nullable=True)
    review_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    clause: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicted_fact_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_fact_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Real, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=datetime.utcnow)
