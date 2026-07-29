"""Pydantic models for Review Intelligence Engine — DOC-004."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UrgencyLevel(str, Enum):
    ROUTINE = "routine"
    NORMAL = "normal"
    ELEVATED = "elevated"
    IMMEDIATE = "immediate"
    EMERGENCY = "emergency"


class EmotionCategory(str, Enum):
    SATISFACTION = "satisfaction"
    DELIGHT = "delight"
    GRATITUDE = "gratitude"
    DISAPPOINTMENT = "disappointment"
    FRUSTRATION = "frustration"
    ANGER = "anger"
    FEAR = "fear"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


class EntityInfo(BaseModel):
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    label: Optional[str] = None
    confidence: float = 0.0
    matched_term: str = ""


class AspectInfo(BaseModel):
    key: str
    label: str
    category: str = "OTHER"
    confidence: float = 0.0
    method: str = "config"


class DepartmentInfo(BaseModel):
    key: str
    label: str
    confidence: float = 0.0


class SentimentInfo(BaseModel):
    label: str  # Positive | Negative | Neutral | Mixed
    score: float = 0.0
    aspect_based: bool = True


class EmotionInfo(BaseModel):
    primary: EmotionCategory = EmotionCategory.NEUTRAL
    branch: str = "neutral"  # positive | negative | neutral
    confidence: float = 0.0


class RootCauseInfo(BaseModel):
    hypothesis: Optional[str] = None
    category: Optional[str] = None  # maintenance | staffing | process | equipment | policy
    confidence: float = 0.0
    is_repeated: bool = False
    is_chronic: bool = False
    trend: Optional[str] = None  # rising | stable | declining | new


class RecommendationInfo(BaseModel):
    action: str
    department: str
    priority: str = "normal"
    sla_hours: Optional[int] = None
    auto_assign: bool = False


class WorkflowTrigger(BaseModel):
    trigger_type: str  # notify_gm | notify_security | incident | maintenance_ticket
    reason: str
    severity: SeverityLevel
    urgency: UrgencyLevel
    recipients: list[str] = Field(default_factory=list)


class ClauseSegment(BaseModel):
    index: int
    text: str
    entities: list[EntityInfo] = Field(default_factory=list)
    aspect: AspectInfo
    department: DepartmentInfo
    sentiment: SentimentInfo
    emotion: EmotionInfo
    severity: SeverityLevel = SeverityLevel.LOW
    urgency: UrgencyLevel = UrgencyLevel.NORMAL
    root_cause: Optional[RootCauseInfo] = None
    recommendation: Optional[RecommendationInfo] = None
    keywords: list[str] = Field(default_factory=list)


class TrendSummary(BaseModel):
    repeated_issues: list[str] = Field(default_factory=list)
    chronic_complaints: list[str] = Field(default_factory=list)
    rising_topics: list[str] = Field(default_factory=list)


class ReviewSummary(BaseModel):
    headline: str = ""
    overall_sentiment: str = "Neutral"
    overall_score: float = 0.0
    is_mixed: bool = False
    clause_count: int = 0
    dominant_department: Optional[str] = None
    max_severity: SeverityLevel = SeverityLevel.LOW
    max_urgency: UrgencyLevel = UrgencyLevel.NORMAL


class ReviewIntelligenceResult(BaseModel):
    review_id: Optional[str] = None
    pipeline_version: str = "1.0.0"
    language: str = "tr"
    raw_text: str
    normalized_text: str = ""
    sentences: list[str] = Field(default_factory=list)
    clauses: list[str] = Field(default_factory=list)
    segments: list[ClauseSegment] = Field(default_factory=list)
    summary: ReviewSummary
    trends: TrendSummary = Field(default_factory=TrendSummary)
    workflow_triggers: list[WorkflowTrigger] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
