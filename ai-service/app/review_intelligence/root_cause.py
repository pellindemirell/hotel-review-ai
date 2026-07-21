"""Root cause analysis stub — trend aggregation hook for v1."""

from __future__ import annotations

import re
from typing import Optional

from app.review_intelligence.models import RootCauseInfo, SeverityLevel

_MAINTENANCE_PATTERNS = (
    (r"\b(klima|hvac|klima\s*calism|klima\s*çalış)\b", "HVAC bakım / arıza", "maintenance"),
    (r"\b(mutfak|sicaklik|sıcaklık|buzdolabi|buzdolabı)\b", "Mutfak sıcaklık / ekipman", "equipment"),
    (r"\b(wifi|internet|ag\s*bagl|ağ\s*bağl)\b", "Ağ altyapısı", "equipment"),
    (r"\b(tikan|tıkan|sizinti|sızıntı|tesisat)\b", "Tesisat arızası", "maintenance"),
    (r"\b(personel|garson|resepsiyon|ilgisiz|kaba)\b", "Personel eğitimi / kadro", "staffing"),
    (r"\b(fiyat|ucret|ücret|fatura|pahali|pahalı)\b", "Fiyatlandırma politikası", "policy"),
)


class RootCauseAnalyzer:
    """Stage 13: Root cause hypothesis + trend flags (stub aggregation)."""

    def __init__(self) -> None:
        self._issue_counts: dict[str, int] = {}

    def analyze(
        self,
        clause: str,
        aspect_key: str,
        severity: SeverityLevel,
    ) -> Optional[RootCauseInfo]:
        text = clause.lower()
        hypothesis: Optional[str] = None
        category: Optional[str] = None

        for pattern, hyp, cat in _MAINTENANCE_PATTERNS:
            if re.search(pattern, text):
                hypothesis = hyp
                category = cat
                break

        if not hypothesis and aspect_key.startswith("hvac"):
            hypothesis = "HVAC bakım / filtre değişimi"
            category = "maintenance"
        elif not hypothesis and aspect_key in ("food_quality", "breakfast_variety"):
            hypothesis = "Mutfak operasyon / menü planlama"
            category = "process"

        if not hypothesis:
            return None

        track_key = f"{aspect_key}:{category}"
        self._issue_counts[track_key] = self._issue_counts.get(track_key, 0) + 1
        count = self._issue_counts[track_key]

        return RootCauseInfo(
            hypothesis=hypothesis,
            category=category,
            confidence=0.65 if severity.value in ("high", "critical") else 0.5,
            is_repeated=count >= 2,
            is_chronic=count >= 5,
            trend="rising" if count >= 3 else ("new" if count == 1 else "stable"),
        )

    def get_trends(self) -> dict[str, list[str]]:
        repeated = [k.split(":")[0] for k, v in self._issue_counts.items() if v >= 2]
        chronic = [k.split(":")[0] for k, v in self._issue_counts.items() if v >= 5]
        rising = [k.split(":")[0] for k, v in self._issue_counts.items() if v >= 3]
        return {
            "repeated_issues": repeated,
            "chronic_complaints": chronic,
            "rising_topics": rising,
        }
