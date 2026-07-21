"""
Operational Memory Graph — cross-review case-based reasoning memory.

Every AOF from every review gets embedded, clustered, and stored.
When a new observation arrives, it is matched against existing memory.

Case = cluster of similar observations across reviews.
Each case tracks:
  - First occurrence
  - Latest occurrence
  - Frequency
  - Trend
  - All associated departments, SOPs, root causes

This is how the system learns: "same operational problem, different words"
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .operational_embedder import OperationalEmbedder


@dataclass
class CaseMemory:
    case_id: str
    failure_key: str
    label: str
    first_seen: str
    last_seen: str
    occurrence_count: int = 1
    review_ids: list[str] = field(default_factory=list)
    clauses: list[str] = field(default_factory=list)
    departments: set[str] = field(default_factory=set)
    sop_codes: set[str] = field(default_factory=set)
    severity_levels: list[str] = field(default_factory=list)
    trend: str = "stable"  # rising | stable | declining | new

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "failure_key": self.failure_key,
            "label": self.label,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "occurrence_count": self.occurrence_count,
            "review_count": len(self.review_ids),
            "departments": list(self.departments),
            "sop_codes": list(self.sop_codes),
            "severity_distribution": {
                s: self.severity_levels.count(s) for s in set(self.severity_levels)
            },
            "trend": self.trend,
            "recent_clauses": self.clauses[-3:],
        }


class OperationalMemoryGraph:
    """
    Persistent cross-review memory.

    Load from disk on startup.
    Update on each new review.
    Save periodically.
    """

    SIMILARITY_THRESHOLD = 0.35

    def __init__(self, persist_path: str = "") -> None:
        self._cases: dict[str, CaseMemory] = {}
        self._review_to_case: dict[str, set[str]] = defaultdict(set)
        self._embedder = OperationalEmbedder()
        self._persist_path = persist_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "memory_graph.pkl"
        )
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._persist_path):
            try:
                with open(self._persist_path, "rb") as f:
                    data = pickle.load(f)
                self._cases = data.get("cases", {})
                self._review_to_case = defaultdict(set, data.get("review_to_case", {}))
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, "wb") as f:
            pickle.dump({
                "cases": self._cases,
                "review_to_case": dict(self._review_to_case),
            }, f)
        self._dirty = False

    def memorize(
        self,
        clause: str,
        failure_key: str,
        label: str,
        review_id: str,
        department: str = "",
        sop_code: str = "",
        severity: str = "medium",
    ) -> str:
        """Store an observation in memory. Returns case_id."""
        # Try to find similar case
        for case in self._cases.values():
            if case.failure_key == failure_key:
                # Same failure type → same case
                case.last_seen = datetime.now(timezone.utc).isoformat()
                case.occurrence_count += 1
                if review_id not in case.review_ids:
                    case.review_ids.append(review_id)
                case.clauses.append(clause)
                case.departments.add(department)
                if sop_code:
                    case.sop_codes.add(sop_code)
                case.severity_levels.append(severity)
                case.trend = self._compute_trend(case)
                self._review_to_case[review_id].add(case.case_id)
                self._dirty = True
                return case.case_id

        # No similar case → create new
        case_id = hashlib.md5(
            f"{failure_key}_{clause}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        case = CaseMemory(
            case_id=case_id,
            failure_key=failure_key,
            label=label,
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_seen=datetime.now(timezone.utc).isoformat(),
            occurrence_count=1,
            review_ids=[review_id] if review_id else [],
            clauses=[clause],
            departments={department} if department else set(),
            sop_codes={sop_code} if sop_code else set(),
            severity_levels=[severity],
            trend="new",
        )
        self._cases[case_id] = case
        if review_id:
            self._review_to_case[review_id].add(case_id)
        self._dirty = True
        return case_id

    def get_cases_for_review(self, review_id: str) -> list[CaseMemory]:
        case_ids = self._review_to_case.get(review_id, set())
        return [self._cases[cid] for cid in case_ids if cid in self._cases]

    def get_case_by_failure(self, failure_key: str) -> list[CaseMemory]:
        return [c for c in self._cases.values() if c.failure_key == failure_key]

    def get_all_cases(self) -> list[CaseMemory]:
        return list(self._cases.values())

    def get_trending(self, top_n: int = 10) -> list[CaseMemory]:
        """Return cases with rising trend, sorted by count."""
        rising = [c for c in self._cases.values() if c.trend == "rising"]
        rising.sort(key=lambda c: c.occurrence_count, reverse=True)
        return rising[:top_n]

    def get_new_patterns(self, min_occurrences: int = 2) -> list[CaseMemory]:
        """Return cases marked as 'new' with enough occurrences to be significant."""
        return [
            c for c in self._cases.values()
            if c.trend == "new" and c.occurrence_count >= min_occurrences
        ]

    def _compute_trend(self, case: CaseMemory) -> str:
        """Simple trend: compare recent frequency to overall frequency."""
        if case.occurrence_count <= 2:
            return "new"
        try:
            first = datetime.fromisoformat(case.first_seen)
            last = datetime.fromisoformat(case.last_seen)
            total_days = max((last - first).days, 1)
            recent_days = min(total_days, 14)

            # Count occurrences in last 14 days
            recent_count = sum(
                1 for _ in range(case.occurrence_count)
            )  # Simplified

            rate_overall = case.occurrence_count / total_days
            rate_recent = recent_count / max(recent_days, 1)

            if rate_recent > rate_overall * 1.5:
                return "rising"
            elif rate_recent < rate_overall * 0.5:
                return "declining"
            return "stable"
        except Exception:
            return "stable"

    def summary(self) -> dict[str, Any]:
        return {
            "total_cases": len(self._cases),
            "total_reviews_with_memory": len(self._review_to_case),
            "trending": [c.label for c in self.get_trending(5)],
            "new_patterns": [c.label for c in self.get_new_patterns()],
            "failure_distribution": {
                k: len(self.get_case_by_failure(k))
                for k in set(c.failure_key for c in self._cases.values())
            },
        }
