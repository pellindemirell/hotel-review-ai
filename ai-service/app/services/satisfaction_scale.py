"""
5 seviyeli Türkçe memnuniyet ölçeği — sentiment skoru veya 1-5 puan eşlemesi.
"""
from __future__ import annotations

from typing import Optional

# En yüksekten en düşüğe (UI sıralaması)
SATISFACTION_LEVELS: list[dict] = [
    {"label": "Çok İyi", "color": "#16a34a", "priority": 5},
    {"label": "İyi", "color": "#84cc16", "priority": 4},
    {"label": "Kararsız", "color": "#ca8a04", "priority": 3},
    {"label": "Az Memnun", "color": "#ea580c", "priority": 2},
    {"label": "Hiç Memnun Değil", "color": "#dc2626", "priority": 1},
]

SATISFACTION_LABELS: list[str] = [level["label"] for level in SATISFACTION_LEVELS]

SATISFACTION_COLORS: dict[str, str] = {level["label"]: level["color"] for level in SATISFACTION_LEVELS}


def empty_satisfaction_counts() -> dict[str, int]:
    """Tüm memnuniyet seviyeleri için sıfır sayaç."""
    return {label: 0 for label in SATISFACTION_LABELS}


def score_to_satisfaction_label(score: float, sentiment: Optional[str] = None) -> str:
    """
    Sentiment skorunu 5 seviyeli Türkçe memnuniyet etiketine çevirir.

    Eşikler:
    - score >= 0.6 veya güçlü olumlu → Çok İyi
    - score >= 0.2 → İyi
    - -0.2 ile 0.2 arası veya Nötr → Kararsız
    - score >= -0.6 → Az Memnun
    - score < -0.6 veya güçlü olumsuz → Hiç Memnun Değil
    """
    if sentiment == "Positive" and score >= 0.65:
        return "Çok İyi"
    if sentiment == "Negative" and score <= -0.65:
        return "Hiç Memnun Değil"
    if score >= 0.6:
        return "Çok İyi"
    if score >= 0.2:
        return "İyi"
    if -0.2 <= score <= 0.2 or sentiment == "Neutral":
        return "Kararsız"
    if score >= -0.6:
        return "Az Memnun"
    return "Hiç Memnun Değil"


def rating_to_satisfaction_label(rating: int) -> str:
    """1-5 yıldız puanını memnuniyet etiketine çevirir."""
    mapping = {
        5: "Çok İyi",
        4: "İyi",
        3: "Kararsız",
        2: "Az Memnun",
        1: "Hiç Memnun Değil",
    }
    return mapping.get(rating, "Kararsız")


def resolve_satisfaction_label(
    score: float,
    sentiment: Optional[str] = None,
    rating: Optional[int] = None,
) -> str:
    """Aspect için önce puan, yoksa sentiment skoru kullanır."""
    if rating is not None and 1 <= rating <= 5:
        return rating_to_satisfaction_label(rating)
    return score_to_satisfaction_label(score, sentiment)
