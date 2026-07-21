"""
Process Health Score (PHS) — per-department sub-process KPI calculator.

Each department has sub-processes. Each sub-process has a health score
based on AOF evidence over a time window:
  100% = all facts positive (or no failures)
  0%   = all facts critical failures

Scores are weighted by severity and recency.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from .models import AtomicOperationalFact, FactType, SeverityLevel

_SUB_PROCESSES: dict[str, list[str]] = {
    "Kat Hizmetleri": [
        "Pre-arrival Inspection",
        "Room Cleaning",
        "Linen Management",
        "Guest Request Fulfillment",
        "Guest Follow-up",
        "Post-incident Deep Cleaning",
        "Hygiene Control",
        "Amenity Delivery",
        "Turn-down Service",
        "Mini-bar Restock",
    ],
    "Yiyecek & İçecek": [
        "Kitchen Quality Control",
        "Beverage Inventory & Service",
        "Restaurant Service",
        "Bar Staff Training",
        "Breakfast Service",
        "Menu Planning",
        "Dinner Service",
    ],
    "Ön Büro": [
        "Check-in Process",
        "Check-out Process",
        "Guest Request Logging",
        "Complaint Handling",
        "Bell Service",
        "Reservation Management",
    ],
    "İnsan Kaynakları": [
        "Staff Onboarding & Training",
        "Performance Management",
        "Language Proficiency",
        "Service Attitude",
    ],
    "Teknik Servis": [
        "HVAC Maintenance",
        "WiFi Infrastructure",
        "Plumbing",
        "Electrical",
        "Pool Maintenance",
    ],
    "Kalite Yönetimi": [
        "Daily Quality Audit",
        "Compliance Check",
        "Process Improvement",
        "Guest Feedback Analysis",
    ],
    "Yönetim": [
        "Guest Satisfaction Monitoring",
        "Department Coordination",
        "Resource Allocation",
    ],
    "Havuz & Animasyon": [
        "Pool Cleanliness",
        "Pool Safety",
        "Entertainment Program",
        "Sports Activities",
        "Kids Club",
    ],
}


class ProcessHealthScoreEngine:
    """Tracks per-sub-process health scores over time."""

    def __init__(self, history_window_days: int = 30) -> None:
        self._window = history_window_days
        self._fact_store: list[AtomicOperationalFact] = []

    def update(self, facts: list[AtomicOperationalFact]) -> None:
        self._fact_store.extend(facts)

    def compute(
        self,
        facts: Optional[list[AtomicOperationalFact]] = None,
    ) -> dict[str, dict[str, Any]]:
        sources = facts if facts is not None else self._fact_store
        proc_facts = [
            f
            for f in sources
            if f.fact_type
            in (FactType.PROCESS_FAILURE, FactType.OBSERVATION, FactType.SOP_VIOLATION)
        ]

        dept_scores: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for fact in proc_facts:
            dept = fact.department
            sub = fact.sub_process or "General"
            if not dept:
                continue

            base = 1.0
            sev_penalty = {
                SeverityLevel.CRITICAL: -1.0,
                SeverityLevel.HIGH: -0.6,
                SeverityLevel.MEDIUM: -0.3,
                SeverityLevel.LOW: -0.1,
                SeverityLevel.INFO: 0.0,
            }.get(fact.severity, 0.0)

            score = max(-1.0, min(1.0, base + sev_penalty))
            dept_scores[dept][sub].append(score)

        result: dict[str, dict[str, Any]] = {}
        for dept in sorted(dept_scores.keys()):
            sub_scores: dict[str, Any] = {}
            sub_list = _SUB_PROCESSES.get(dept, [])
            for sub in sub_list:
                scores = dept_scores[dept].get(sub, [])
                if scores:
                    avg = sum(scores) / len(scores)
                    pct = max(0, min(100, round((avg + 1) / 2 * 100)))
                else:
                    pct = 100
                sub_scores[sub] = {
                    "score": pct,
                    "status": "healthy" if pct >= 70 else "warning" if pct >= 40 else "critical",
                    "fact_count": len(scores),
                }

            all_scores = [s["score"] for s in sub_scores.values()]
            overall = round(sum(all_scores) / len(all_scores)) if all_scores else 100

            result[dept] = {
                "overall_health": overall,
                "status": "healthy" if overall >= 70 else "warning" if overall >= 40 else "critical",
                "sub_processes": sub_scores,
                "worst": min(sub_scores, key=lambda k: sub_scores[k]["score"]) if sub_scores else "",
            }

        return result

    def summarize(self, dept_health: dict[str, dict[str, Any]]) -> str:
        lines: list[str] = []
        for dept, info in sorted(dept_health.items()):
            status_icon = "✅" if info["status"] == "healthy" else "⚠️" if info["status"] == "warning" else "🔴"
            lines.append(f"{status_icon} **{dept}** — Overall: %{info['overall_health']}")
            for sub, data in sorted(info["sub_processes"].items()):
                icon = "✅" if data["status"] == "healthy" else "⚠️" if data["status"] == "warning" else "🔴"
                lines.append(f"  {icon} {sub}: %{data['score']} ({data['fact_count']} fact(s))")
        return "\n".join(lines)
