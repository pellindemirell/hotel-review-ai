"""
Atomic Operational Fact (AOF) — Hotel Operational Decision Intelligence Platform.

Every operational insight from a guest review is decomposed into AOFs.
Each AOF is: observed → evidenced → chained → actionable → learnable.

No data is stored as bare sentiment. Every fact has:
  - evidence (exact guest quote)
  - confidence (ml + rule hybrid)
  - chain position (what caused this? what does this cause?)
  - SOP / role / process mapping
  - operational & financial impact
  - recovery analysis
  - guest journey context
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class FactType(str, Enum):
    OBSERVATION = "observation"
    GUEST_IMPACT = "guest_impact"
    PROCESS_FAILURE = "process_failure"
    SUB_PROCESS = "sub_process"
    SOP_VIOLATION = "sop_violation"
    ROOT_CAUSE = "root_cause"
    BUSINESS_IMPACT = "business_impact"
    ACTION = "action"
    RECOVERY_ATTEMPT = "recovery_attempt"
    RECOVERY_FAILURE = "recovery_failure"
    DEPENDENCY_ISSUE = "dependency_issue"
    ESCALATION = "escalation"
    TRAINING_GAP = "training_gap"
    FINANCIAL_RISK = "financial_risk"
    NEW_PATTERN = "new_pattern"
    JOURNEY_IMPACT = "journey_impact"


class SeverityLevel(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuestJourneyPhase(str, Enum):
    PRE_ARRIVAL = "pre_arrival"
    ARRIVAL = "arrival"
    STAY = "stay"
    DEPARTURE = "departure"
    POST_STAY = "post_stay"


class RecoveryStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    ATTEMPTED_SUCCESSFUL = "attempted_successful"
    ATTEMPTED_PARTIAL = "attempted_partial"
    ATTEMPTED_FAILED = "attempted_failed"
    ATTEMPTED_WORSENED = "attempted_worsened"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Evidence:
    clause: str
    normalized_clause: str
    confidence: float
    matched_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause": self.clause,
            "normalized_clause": self.normalized_clause,
            "confidence": self.confidence,
            "matched_terms": self.matched_terms,
        }


@dataclass
class SOPReference:
    code: str
    step_number: Optional[int] = None
    step_name: Optional[str] = None
    step_skipped: bool = False
    department: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "step_number": self.step_number,
            "step_name": self.step_name,
            "step_skipped": self.step_skipped,
            "department": self.department,
        }


@dataclass
class OperationalImpact:
    guest_effort_score: int = 1
    mood_impact: int = 0
    reputation_risk: RiskLevel = RiskLevel.NONE
    repeat_customer_risk: RiskLevel = RiskLevel.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "guest_effort_score": self.guest_effort_score,
            "mood_impact": self.mood_impact,
            "reputation_risk": self.reputation_risk.value,
            "repeat_customer_risk": self.repeat_customer_risk.value,
        }


@dataclass
class FinancialImpact:
    revenue_risk: RiskLevel = RiskLevel.NONE
    ota_visibility_risk: RiskLevel = RiskLevel.NONE
    brand_risk: RiskLevel = RiskLevel.NONE
    estimated_loss_try: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "revenue_risk": self.revenue_risk.value,
            "ota_visibility_risk": self.ota_visibility_risk.value,
            "brand_risk": self.brand_risk.value,
            "estimated_loss_try": self.estimated_loss_try,
        }


@dataclass
class EscalationInfo:
    required: bool = False
    level: str = ""
    notify_roles: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "level": self.level,
            "notify_roles": self.notify_roles,
            "reason": self.reason,
        }


@dataclass
class RecoveryAnalysis:
    status: RecoveryStatus = RecoveryStatus.NOT_ATTEMPTED
    attempt_description: str = ""
    failure_reason: str = ""
    guest_satisfaction_after: str = ""
    gap: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "attempt_description": self.attempt_description,
            "failure_reason": self.failure_reason,
            "guest_satisfaction_after": self.guest_satisfaction_after,
            "gap": self.gap,
        }


@dataclass
class DependencyNode:
    department: str
    process: str
    status: str  # completed | failed | blocked | not_started
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "process": self.process,
            "status": self.status,
            "confidence": self.confidence,
        }


@dataclass
class LearningSignal:
    is_new_pattern: bool = False
    pattern_id: str = ""
    pattern_description: str = ""
    occurrences: int = 1
    trend: str = "new"

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_new_pattern": self.is_new_pattern,
            "pattern_id": self.pattern_id,
            "pattern_description": self.pattern_description,
            "occurrences": self.occurrences,
            "trend": self.trend,
        }


@dataclass
class AtomicOperationalFact:
    fact_id: str
    fact_type: FactType
    label: str
    description: str
    evidence: list[Evidence]

    # ML
    confidence: float

    # Chain position
    parent_fact_ids: list[str] = field(default_factory=list)
    child_fact_ids: list[str] = field(default_factory=list)

    # Department
    department: str = ""
    sub_process: str = ""

    # SOP
    sop: Optional[SOPReference] = None

    # Role
    responsible_role: str = ""

    # Impact
    severity: SeverityLevel = SeverityLevel.INFO
    operational_impact: OperationalImpact = field(default_factory=OperationalImpact)
    financial_impact: FinancialImpact = field(default_factory=FinancialImpact)

    # Root cause
    root_cause_candidates: list[str] = field(default_factory=list)

    # Recovery
    recovery: RecoveryAnalysis = field(default_factory=RecoveryAnalysis)

    # Dependency
    dependency_chain: list[DependencyNode] = field(default_factory=list)
    dependency_break: Optional[str] = None

    # Escalation
    escalation: EscalationInfo = field(default_factory=EscalationInfo)

    # Guest journey
    journey_phase: Optional[GuestJourneyPhase] = None
    journey_cascade: Optional[str] = None

    # Learning
    learning: LearningSignal = field(default_factory=LearningSignal)

    # Action
    recommended_action: str = ""
    action_owner: str = ""

    # Metadata
    source_review_id: str = ""
    source_clause_index: int = -1
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "fact_type": self.fact_type.value,
            "label": self.label,
            "description": self.description,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "parent_fact_ids": self.parent_fact_ids,
            "child_fact_ids": self.child_fact_ids,
            "department": self.department,
            "sub_process": self.sub_process,
            "sop": self.sop.to_dict() if self.sop else None,
            "responsible_role": self.responsible_role,
            "severity": self.severity.value,
            "operational_impact": self.operational_impact.to_dict(),
            "financial_impact": self.financial_impact.to_dict(),
            "root_cause_candidates": self.root_cause_candidates,
            "recovery": self.recovery.to_dict(),
            "dependency_chain": [n.to_dict() for n in self.dependency_chain],
            "dependency_break": self.dependency_break,
            "escalation": self.escalation.to_dict(),
            "journey_phase": self.journey_phase.value if self.journey_phase else None,
            "journey_cascade": self.journey_cascade,
            "learning": self.learning.to_dict(),
            "recommended_action": self.recommended_action,
            "action_owner": self.action_owner,
            "source_review_id": self.source_review_id,
            "source_clause_index": self.source_clause_index,
            "created_at": self.created_at,
        }
