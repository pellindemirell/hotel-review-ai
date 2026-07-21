"""
Yönetici dashboard için analiz edilmiş yorum deposu.
JSON dosyasına kalıcılık + demo seed desteği.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.satisfaction_scale import empty_satisfaction_counts, SATISFACTION_LABELS

_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "manager_review_store.json",
)

_lock = threading.Lock()


@dataclass
class StoredReview:
    id: str
    comment: str
    rating: Optional[int]
    sentiment: str
    sentiment_score: float
    category: str
    confidence: float
    keywords: list[str]
    summary: str
    suggestion: str
    is_mixed: bool = False
    secondary_category: Optional[str] = None
    is_manipulation: bool = False
    source: str = "demo"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 55 demo yorum — tüm departmanlar + karışık/ informal örnekler
DEMO_REVIEWS: list[tuple[str, Optional[int]]] = [
    ("oda tertemizdi havlular taze", 5),
    ("banyo pırıl pırıl temizlik harika", 5),
    ("oda kirliydi çarşaflar lekeli", 2),
    ("havlu lekeli banyo pis kokuyordu", 1),
    ("yatak kirli toz her yerde", 2),
    ("temizlik yapılmamış oda dağınık", 2),
    ("oda pis la çöp gibi", 1),
    ("domates çorbası harikaydı", 5),
    ("kahvaltı mükemmeldi taze peynir bol", 5),
    ("yemek soğuk geldi lezzetsizdi", 2),
    ("kahvaltı berbat az çeşit vardı", 2),
    ("açık büfe lezzetsiz yemek soğuktu", 1),
    ("yemekler o kadar kötüydü ki bayılacaktım", 2),
    ("yemek berbat valla aga", 2),
    ("otel efsane aga tavsiye", 5),
    ("garson çok kaba davrandı", 2),
    ("personel ilgisiz ve yavaş", 2),
    ("garson güler yüzlü yardımsever", 5),
    ("resepsiyonist saygısız konuştu", 2),
    ("personel kibar check-in hızlı", 5),
    ("klima bozuk oda çok sıcak", 2),
    ("wifi çalışmıyor internet yok", 2),
    ("tv bozuk kumanda çalışmıyor", 2),
    ("asansör bozuk kata çıkamadık", 1),
    ("klima çalışmıyo harbiden", 2),
    ("klima çok soğuktu ama havuzu çok beğendik", 3),
    ("havuz kirli klor çok fazla", 2),
    ("masaj harikaydı spa mükemmel", 5),
    ("plaj güzel animasyon eğlenceli", 5),
    ("havuz temiz deniz manzarası harika", 5),
    ("animasyon gürültülü gece uyuyamadık", 2),
    ("check-in çok yavaş saatlerce bekledik", 2),
    ("giriş kolaydı resepsiyon hızlı", 5),
    ("rezervasyon hatası oda hazır değildi", 2),
    ("lobide giriş sorunsuz bellboy ilgili", 5),
    ("fatura hatası yaptılar", 2),
    ("fiyat fahiş ekstra ücret", 2),
    ("depozito iade edilmedi", 1),
    ("fiyat performans iyi uygun fiyat", 4),
    ("gizli masraf checkout fatura şoku", 1),
    ("herşey mükemmeldi süper tatil", 5),
    ("harika tatil tavsiye ederim", 5),
    ("asla gelmeyin pişman olduk", 1),
    ("mükemmel bir deneyim tekrar geliriz", 5),
    ("fena değil işte idare eder", 3),
    ("10/10 mükemmel otel", 5),
    ("rezalet la bir daha gitmem", 1),
    ("oda kirli ama yemek harika", 3),
    ("yemek harika garson kaba", 3),
    ("odalar çok pisti ama yemeklere bayıldık, masaj keyifliydi", 3),
    ("klima bozuk fakat personel kibar, kahvaltı harikaydı", 3),
    ("banyo pis wifi yok fatura hatalı", 1),
    ("spa harika yemek enfes personel ilgili", 5),
    ("inşaat gürültüsü vardı ama oda temizdi", 3),
    ("5 yıldız veriyorum öne çıksın diye oda berbat", 5),
    ("burada keyiften ölebilirim cennet gibi", 5),
]


class ReviewStore:
    """Thread-safe in-memory + JSON kalıcı yorum deposu."""

    def __init__(self, path: str = _STORE_PATH) -> None:
        self.path = path
        self._reviews: list[StoredReview] = []
        self._department_absa: dict[str, dict[str, Any]] = {}
        self._entity_absa: dict[str, dict[str, Any]] = {}
        self._domain_absa: dict[str, dict[str, Any]] = {}
        self._load()

    def _empty_dept_block(self) -> dict[str, Any]:
        return {
            "total": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "satisfaction": empty_satisfaction_counts(),
        }

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.isfile(self.path):
            self._reviews = []
            self._department_absa = {}
            self._entity_absa = {}
            self._domain_absa = {}
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self._reviews = [StoredReview(**r) for r in raw.get("reviews", [])]
            self._department_absa = raw.get("department_absa", {})
            self._entity_absa = raw.get("entity_absa", {})
            self._domain_absa = raw.get("domain_absa", {})
            for store_dict in (self._department_absa, self._entity_absa, self._domain_absa):
                for _, block in store_dict.items():
                    if "satisfaction" not in block:
                        block["satisfaction"] = empty_satisfaction_counts()
                    for label in SATISFACTION_LABELS:
                        block["satisfaction"].setdefault(label, 0)
        except (OSError, json.JSONDecodeError, TypeError):
            self._reviews = []
            self._department_absa = {}
            self._entity_absa = {}
            self._domain_absa = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, encoding="utf-8", mode="w") as f:
            json.dump(
                {
                    "version": 2,
                    "count": len(self._reviews),
                    "reviews": [r.to_dict() for r in self._reviews],
                    "department_absa": self._department_absa,
                    "entity_absa": self._entity_absa,
                    "domain_absa": self._domain_absa,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def count(self) -> int:
        with _lock:
            return len(self._reviews)

    def all_reviews(self) -> list[StoredReview]:
        with _lock:
            return list(self._reviews)

    def add(self, review: StoredReview) -> StoredReview:
        with _lock:
            self._reviews.append(review)
            self._save()
        return review

    def add_from_analysis(
        self,
        comment: str,
        rating: Optional[int],
        analysis: dict[str, Any],
        source: str = "live",
        created_at: Optional[str] = None,
    ) -> StoredReview:
        item = StoredReview(
            id=str(uuid.uuid4())[:8],
            comment=comment,
            rating=rating,
            sentiment=analysis.get("sentiment", "Neutral"),
            sentiment_score=float(analysis.get("sentimentScore", analysis.get("sentiment_score", 0))),
            category=analysis.get("category", "Diğer"),
            confidence=float(analysis.get("confidence", 0.5)),
            keywords=list(analysis.get("keywords", [])),
            summary=analysis.get("summary", ""),
            suggestion=analysis.get("suggestion", ""),
            is_mixed=bool(analysis.get("isMixedReview", analysis.get("is_mixed", False))),
            secondary_category=analysis.get("secondaryCategory", analysis.get("secondary_category")),
            is_manipulation=bool(analysis.get("isManipulation", analysis.get("is_manipulation", False))),
            source=source,
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
        )
        return self.add(item)

    def clear(self) -> None:
        with _lock:
            self._reviews = []
            self._department_absa = {}
            self._entity_absa = {}
            self._domain_absa = {}
            self._save()

    def department_absa_summary(self) -> dict[str, dict[str, Any]]:
        with _lock:
            return json.loads(json.dumps(self._department_absa, ensure_ascii=False))

    def entity_absa_summary(self) -> dict[str, dict[str, Any]]:
        with _lock:
            return json.loads(json.dumps(self._entity_absa, ensure_ascii=False))

    def domain_absa_summary(self) -> dict[str, dict[str, Any]]:
        with _lock:
            return json.loads(json.dumps(self._domain_absa, ensure_ascii=False))

    def _accumulate_aspect(
        self,
        store: dict[str, dict[str, Any]],
        key: str,
        aspect: dict[str, Any],
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        sentiment = (aspect.get("sentiment") or "Neutral").lower()
        satisfaction = aspect.get("satisfactionLevel") or aspect.get("satisfaction_level")
        if not satisfaction:
            from app.services.satisfaction_scale import resolve_satisfaction_label
            satisfaction = resolve_satisfaction_label(
                float(aspect.get("sentimentScore", aspect.get("sentiment_score", 0))),
                aspect.get("sentiment"),
                aspect.get("rating"),
            )
        block = store.setdefault(key, {**self._empty_dept_block(), **(extra or {})})
        block["total"] += 1
        if sentiment in block:
            block[sentiment] += 1
        if satisfaction in block["satisfaction"]:
            block["satisfaction"][satisfaction] += 1

    def add_absa_aspects(self, review_id: str, aspects: list[dict[str, Any]]) -> None:
        """ABSA aspect'lerini birim, entity ve domain agregasyonuna ekler."""
        if not aspects:
            return
        with _lock:
            for aspect in aspects:
                dept = aspect.get("department") or aspect.get("departmentLabel") or aspect.get("category") or "Diğer"
                self._accumulate_aspect(self._department_absa, dept, aspect)

                entity = aspect.get("entity") or {}
                etype = aspect.get("entityType") or entity.get("type") or "generic_unit"
                eid = aspect.get("entityId") or entity.get("id") or "default"
                entity_key = f"{etype}:{eid}"
                self._accumulate_aspect(
                    self._entity_absa,
                    entity_key,
                    aspect,
                    extra={
                        "entity_type": etype,
                        "entity_id": eid if eid != "default" else None,
                        "domain": aspect.get("domain", "hotel"),
                    },
                )

                domain = aspect.get("domain") or "hotel"
                self._accumulate_aspect(
                    self._domain_absa,
                    domain,
                    aspect,
                    extra={"domain_label": aspect.get("domainLabel", domain)},
                )
            self._save()

    def seed_demo_if_empty(self, analyze_fn) -> int:
        """Depo boşsa 55 demo yorumu analiz edip yükler."""
        with _lock:
            if self._reviews:
                return 0
        added = 0
        now = datetime.now(timezone.utc)
        total = len(DEMO_REVIEWS)
        for i, (comment, rating) in enumerate(DEMO_REVIEWS):
            days_ago = 13 - int(i * 13 / max(total - 1, 1))
            created = (now - timedelta(days=days_ago, hours=i % 8)).isoformat()
            result = analyze_fn(comment, rating)
            self.add_from_analysis(comment, rating, result, source="demo", created_at=created)
            added += 1
        return added


# Singleton
_store: Optional[ReviewStore] = None


def get_review_store() -> ReviewStore:
    global _store
    if _store is None:
        _store = ReviewStore()
    return _store
