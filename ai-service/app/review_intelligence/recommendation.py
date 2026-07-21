"""Action recommendation engine — automatic operational suggestions."""

from __future__ import annotations

from app.review_intelligence.models import (
    RecommendationInfo,
    SeverityLevel,
    UrgencyLevel,
    WorkflowTrigger,
)
from app.services.rag_service import RagService
from app.services.keyword_service import KeywordService


class RecommendationEngine:
    """Stage 14: Action recommendations + optional workflow triggers."""

    _SLA_MAP = {
        UrgencyLevel.EMERGENCY: 0,
        UrgencyLevel.IMMEDIATE: 1,
        UrgencyLevel.ELEVATED: 4,
        UrgencyLevel.NORMAL: 24,
        UrgencyLevel.ROUTINE: 72,
    }

    def recommend(
        self,
        clause: str,
        department_label: str,
        sentiment_label: str,
        severity: SeverityLevel,
        urgency: UrgencyLevel,
        aspect_key: str,
    ) -> RecommendationInfo:
        keywords = KeywordService.extract_keywords(clause, max_keywords=3)
        suggestion = RagService.generate_suggestion(
            category=department_label,
            text=clause,
            keywords=keywords,
            sentiment=sentiment_label,
            is_mixed=False,
            secondary_category=None,
            is_manipulation=False,
        )

        priority = "critical" if severity == SeverityLevel.CRITICAL else (
            "high" if severity == SeverityLevel.HIGH else "normal"
        )

        auto_assign = urgency in (UrgencyLevel.EMERGENCY, UrgencyLevel.IMMEDIATE)

        return RecommendationInfo(
            action=suggestion,
            department=department_label,
            priority=priority,
            sla_hours=self._SLA_MAP.get(urgency, 24),
            auto_assign=auto_assign,
        )

    def workflow_triggers(
        self,
        clause: str,
        severity: SeverityLevel,
        urgency: UrgencyLevel,
    ) -> list[WorkflowTrigger]:
        triggers: list[WorkflowTrigger] = []
        lower = clause.lower()

        if urgency == UrgencyLevel.EMERGENCY or (
            severity == SeverityLevel.CRITICAL and "yang" in lower
        ):
            triggers.append(WorkflowTrigger(
                trigger_type="incident",
                reason="Acil güvenlik olayı — yangın/alarm",
                severity=severity,
                urgency=urgency,
                recipients=["gm", "security", "engineering"],
            ))
            triggers.append(WorkflowTrigger(
                trigger_type="notify_gm",
                reason="Genel müdür bilgilendirme — kritik olay",
                severity=severity,
                urgency=urgency,
                recipients=["gm"],
            ))
            triggers.append(WorkflowTrigger(
                trigger_type="notify_security",
                reason="Güvenlik ekibi — acil müdahale",
                severity=severity,
                urgency=urgency,
                recipients=["security"],
            ))
        elif severity == SeverityLevel.CRITICAL:
            triggers.append(WorkflowTrigger(
                trigger_type="maintenance_ticket",
                reason="Kritik teknik arıza",
                severity=severity,
                urgency=urgency,
                recipients=["engineering", "duty_manager"],
            ))

        return triggers
