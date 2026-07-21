"""
HODIP Engine — Hotel Operational Decision Intelligence Platform.

Orchestrates:
  1. Clause splitting (from existing turkish_nlp_utils)
  2. AOF Knowledge Graph construction (knowledge_graph.py)
  3. Process Health Score (process_health.py)
  4. Evidence consolidation & cross-review pattern detection
  5. Final operational report generation
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..services.absa_service import split_clauses_absa

from .knowledge_graph import KnowledgeGraphBuilder
from .models import AtomicOperationalFact, FactType, SeverityLevel
from .process_health import ProcessHealthScoreEngine


class HodipEngine:
    """Main HODIP engine — processes a review into operational intelligence."""

    def __init__(self) -> None:
        self._kg = KnowledgeGraphBuilder()
        self._phs = ProcessHealthScoreEngine()

    def analyze(
        self,
        comment: str,
        review_id: str = "",
        rating: Optional[int] = None,
        language: str = "tr",
    ) -> dict[str, Any]:
        # 1. Split into clauses
        clauses = split_clauses_absa(comment)

        # 2. Build AOF Knowledge Graph
        facts = self._kg.build(clauses, review_id, rating)
        self._phs.update(facts)

        # 3. Compute Process Health Scores
        health = self._phs.compute(facts)

        # 4. Consolidate evidence per department
        evidence_by_dept = self._consolidate_evidence(facts)

        # 5. Cross-review patterns (stub — needs persistent store)
        new_patterns = [f for f in facts if f.fact_type == FactType.NEW_PATTERN]

        # 6. Build report
        return self._build_report(
            comment=comment,
            clauses=clauses,
            facts=facts,
            health=health,
            evidence_by_dept=evidence_by_dept,
            new_patterns=new_patterns,
            language=language,
        )

    def _consolidate_evidence(
        self, facts: list[AtomicOperationalFact]
    ) -> dict[str, list[dict[str, Any]]]:
        by_dept: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            if not fact.department:
                continue
            if fact.department not in by_dept:
                by_dept[fact.department] = []
            for ev in fact.evidence:
                by_dept[fact.department].append({
                    "fact_id": fact.fact_id,
                    "fact_type": fact.fact_type.value,
                    "label": fact.label,
                    "evidence": ev.clause,
                    "confidence": ev.confidence,
                    "severity": fact.severity.value,
                    "sub_process": fact.sub_process,
                })
        return by_dept

    def _build_report(
        self,
        comment: str,
        clauses: list[str],
        facts: list[AtomicOperationalFact],
        health: dict[str, dict[str, Any]],
        evidence_by_dept: dict[str, list[dict[str, Any]]],
        new_patterns: list[AtomicOperationalFact],
        language: str,
    ) -> dict[str, Any]:
        # Facts by type
        observations = [f for f in facts if f.fact_type == FactType.OBSERVATION]
        process_failures = [f for f in facts if f.fact_type == FactType.PROCESS_FAILURE]
        sop_violations = [f for f in facts if f.fact_type == FactType.SOP_VIOLATION]
        root_causes = [f for f in facts if f.fact_type == FactType.ROOT_CAUSE]
        actions = [f for f in facts if f.fact_type == FactType.ACTION]
        recoveries = [
            f for f in facts if f.fact_type
            in (FactType.RECOVERY_ATTEMPT, FactType.RECOVERY_FAILURE)
        ]
        escalations = [f for f in facts if f.fact_type == FactType.ESCALATION]
        financials = [f for f in facts if f.fact_type == FactType.FINANCIAL_RISK]
        deps = [f for f in facts if f.fact_type == FactType.DEPENDENCY_ISSUE]
        journey_impacts = [f for f in facts if f.fact_type == FactType.JOURNEY_IMPACT]
        training_gaps = [f for f in facts if f.fact_type == FactType.TRAINING_GAP]

        max_sev = SeverityLevel.INFO
        for f in facts:
            sev_order = [SeverityLevel.INFO, SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH, SeverityLevel.CRITICAL]
            if sev_order.index(f.severity) > sev_order.index(max_sev):
                max_sev = f.severity

        return {
            "version": "2.0.0",
            "paradigm": "operational_intelligence",
            "platform": "Hotel Operational Decision Intelligence Platform (HODIP)",
            "comment": comment,
            "clauses": clauses,
            "summary": {
                "clause_count": len(clauses),
                "fact_count": len(facts),
                "max_severity": max_sev.value,
                "max_escalation": max(
                    (e.escalation.level for e in escalations),
                    default="none",
                ),
                "recovery_attempted": any(r.recovery.status != "not_attempted" for r in recoveries),
                "new_patterns_found": len(new_patterns),
                "has_process_failures": len(process_failures) > 0,
                "has_sop_violations": len(sop_violations) > 0,
                "has_financial_risk": len(financials) > 0,
            },
            "facts": {
                "observations": [f.to_dict() for f in observations],
                "guest_impacts": [
                    f.to_dict() for f in facts if f.fact_type == FactType.GUEST_IMPACT
                ],
                "process_failures": [f.to_dict() for f in process_failures],
                "sub_processes": [
                    f.to_dict() for f in facts if f.fact_type == FactType.SUB_PROCESS
                ],
                "sop_violations": [f.to_dict() for f in sop_violations],
                "root_causes": [f.to_dict() for f in root_causes],
                "business_impacts": [
                    f.to_dict() for f in facts if f.fact_type == FactType.BUSINESS_IMPACT
                ],
                "actions": [f.to_dict() for f in actions],
                "recoveries": [f.to_dict() for f in recoveries],
                "escalations": [f.to_dict() for f in escalations],
                "financial_risks": [f.to_dict() for f in financials],
                "dependency_issues": [f.to_dict() for f in deps],
                "journey_impacts": [f.to_dict() for f in journey_impacts],
                "training_gaps": [f.to_dict() for f in training_gaps],
                "new_patterns": [f.to_dict() for f in new_patterns],
            },
            "process_health": health,
            "evidence": evidence_by_dept,
            "action_items": [
                {
                    "fact_id": a.fact_id,
                    "action": a.recommended_action,
                    "owner": a.action_owner,
                    "severity": a.severity.value,
                }
                for a in actions
                if a.recommended_action
            ],
            "escalation_chain": [
                {
                    "fact_id": e.fact_id,
                    "reason": e.escalation.reason,
                    "notify": e.escalation.notify_roles,
                    "level": e.escalation.level,
                }
                for e in escalations
            ],
        }
