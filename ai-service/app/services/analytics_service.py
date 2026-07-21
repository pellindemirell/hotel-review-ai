"""
Yönetici dashboard analitik servisi — toplu istatistik, öneri ve yönetici özeti.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.rag_service import RagService
from app.services.review_store import ReviewStore, StoredReview, get_review_store
from app.services.satisfaction_scale import SATISFACTION_COLORS, SATISFACTION_LABELS
from app.services.turkish_nlp_utils import (
    CAT_CLEANING,
    CAT_FOOD,
    CAT_RECEPTION,
    CAT_SPA,
    CAT_STAFF,
    CAT_TECH,
)

# Rol → departman eşlemesi (kısmi eşleşme)
ROLE_DEPARTMENTS: dict[str, Optional[list[str]]] = {
    "genel_mudur": None,
    "crm": None,
    "housekeeping": [CAT_CLEANING],
    "fb": [CAT_FOOD],
    "personel": [CAT_STAFF],
    "teknik": [CAT_TECH],
    "spa": [CAT_SPA],
    "on_buro": [CAT_RECEPTION],
}

CATEGORY_SHORT: dict[str, str] = {
    CAT_CLEANING: "temizlik",
    CAT_FOOD: "yemek",
    CAT_STAFF: "personel",
    CAT_TECH: "teknik",
    CAT_SPA: "spa",
    CAT_RECEPTION: "resepsiyon",
}


class AnalyticsService:
    """Depolanmış yorumlardan dashboard metrikleri üretir."""

    @classmethod
    def _reviews(cls, store: Optional[ReviewStore] = None, role: Optional[str] = None) -> list[StoredReview]:
        items = (store or get_review_store()).all_reviews()
        if not role:
            return items
        return cls.filter_by_role(items, role)

    @classmethod
    def filter_by_role(cls, reviews: list[StoredReview], role: str) -> list[StoredReview]:
        depts = ROLE_DEPARTMENTS.get(role)
        if not depts:
            return reviews
        return [r for r in reviews if any(d in r.category for d in depts)]

    @staticmethod
    def _parse_dt(value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @classmethod
    def compute_stats(
        cls,
        store: Optional[ReviewStore] = None,
        role: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> dict[str, Any]:
        reviews = cls._reviews(store, role)
        total = len(reviews)
        store_obj = store or get_review_store()
        dept_satisfaction = cls._department_satisfaction_breakdown(store_obj, role, domain)
        entity_satisfaction = cls._entity_satisfaction_breakdown(store_obj, domain)
        domain_satisfaction = cls._domain_satisfaction_breakdown(store_obj)

        if total == 0:
            empty = cls._empty_stats()
            empty["department_satisfaction_breakdown"] = dept_satisfaction
            empty["entity_satisfaction_breakdown"] = entity_satisfaction
            empty["domain_satisfaction_breakdown"] = domain_satisfaction
            empty["domain_filter"] = domain
            return empty

        sent_counter = Counter(r.sentiment for r in reviews)
        cat_counter = Counter(r.category for r in reviews)
        neg = sent_counter.get("Negative", 0)
        pos = sent_counter.get("Positive", 0)
        neu = sent_counter.get("Neutral", 0)

        kw_counter: Counter = Counter()
        for r in reviews:
            kw_counter.update(r.keywords)

        dept_sent: dict[str, dict[str, int]] = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
        for r in reviews:
            block = dept_sent[r.category]
            block["total"] += 1
            key = r.sentiment.lower()
            if key in block:
                block[key] += 1

        mixed_count = sum(1 for r in reviews if r.is_mixed)
        manip_count = sum(1 for r in reviews if r.is_manipulation)
        avg_conf = round(sum(r.confidence for r in reviews) / total, 3)
        avg_score = round(sum(r.sentiment_score for r in reviews) / total, 3)

        ratings = [r.rating for r in reviews if r.rating is not None]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        return {
            "total": total,
            "role": role,
            "domain_filter": domain,
            "sentiment": {
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "positive_pct": round(pos / total * 100, 1),
                "negative_pct": round(neg / total * 100, 1),
                "neutral_pct": round(neu / total * 100, 1),
            },
            "category_distribution": [
                {"department": cat, "count": cnt, "pct": round(cnt / total * 100, 1)}
                for cat, cnt in cat_counter.most_common()
            ],
            "department_sentiment": dict(dept_sent),
            "department_satisfaction_breakdown": dept_satisfaction,
            "entity_satisfaction_breakdown": entity_satisfaction,
            "domain_satisfaction_breakdown": domain_satisfaction,
            "category_positive_rates": cls._category_positive_rates(dept_sent),
            "top_keywords": [{"keyword": k, "count": c} for k, c in kw_counter.most_common(20)],
            "top_negative_keywords": cls.top_negative_keywords(reviews, limit=10),
            "trends": cls.compute_trends(reviews),
            "mixed_review_count": mixed_count,
            "manipulation_count": manip_count,
            "avg_confidence": avg_conf,
            "avg_sentiment_score": avg_score,
            "avg_rating": avg_rating,
        }

    @classmethod
    def _empty_stats(cls) -> dict[str, Any]:
        return {
            "total": 0,
            "role": None,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0, "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0},
            "category_distribution": [],
            "department_sentiment": {},
            "department_satisfaction_breakdown": [],
            "entity_satisfaction_breakdown": [],
            "domain_satisfaction_breakdown": [],
            "category_positive_rates": [],
            "top_keywords": [],
            "top_negative_keywords": [],
            "trends": [],
            "mixed_review_count": 0,
            "manipulation_count": 0,
            "avg_confidence": 0,
            "avg_sentiment_score": 0,
            "avg_rating": None,
        }

    @classmethod
    def _category_positive_rates(cls, dept_sent: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        rates = []
        for dept, block in dept_sent.items():
            total = block.get("total", 0)
            if total == 0:
                continue
            pos_pct = round(block.get("positive", 0) / total * 100, 1)
            rates.append({
                "department": dept,
                "positive_pct": pos_pct,
                "total": total,
                "short_name": CATEGORY_SHORT.get(dept, dept.split("&")[0].strip().lower()),
            })
        rates.sort(key=lambda x: -x["total"])
        return rates

    @classmethod
    def _department_satisfaction_breakdown(
        cls,
        store: ReviewStore,
        role: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """ABSA birim agregasyonundan memnuniyet dağılımı."""
        raw = store.department_absa_summary()
        if not raw:
            return []

        depts_filter = ROLE_DEPARTMENTS.get(role or "")
        items: list[dict[str, Any]] = []
        for dept, block in raw.items():
            if depts_filter and not any(d in dept for d in depts_filter):
                continue
            total = block.get("total", 0)
            if total == 0:
                continue
            sat = block.get("satisfaction", {})
            levels = [
                {
                    "label": label,
                    "count": sat.get(label, 0),
                    "color": SATISFACTION_COLORS.get(label, "#94a3b8"),
                }
                for label in SATISFACTION_LABELS
            ]
            items.append({
                "department": dept,
                "total": total,
                "positive": block.get("positive", 0),
                "negative": block.get("negative", 0),
                "satisfaction": sat,
                "levels": levels,
                "short_name": CATEGORY_SHORT.get(dept, dept.split("&")[0].strip().lower()),
            })
        items.sort(key=lambda x: -x["total"])
        return items

    @classmethod
    def _entity_satisfaction_breakdown(
        cls,
        store: ReviewStore,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Alan/entity bazlı memnuniyet dağılımı."""
        raw = store.entity_absa_summary()
        if not raw:
            return []

        entity_labels = {
            "room": "Oda",
            "pool": "Havuz",
            "restaurant": "Restoran",
            "lobby": "Lobi",
            "spa": "Spa",
            "bar": "Bar",
            "wifi_zone": "WiFi Alanı",
            "parking": "Otopark",
            "elevator": "Asansör",
            "floor": "Kat",
            "building": "Bina",
            "generic_unit": "Genel Alan",
        }

        items: list[dict[str, Any]] = []
        for key, block in raw.items():
            etype = block.get("entity_type", key.split(":")[0])
            eid = block.get("entity_id")
            if domain and block.get("domain") and block.get("domain") != domain:
                continue
            total = block.get("total", 0)
            if total == 0:
                continue
            base = entity_labels.get(etype, etype)
            label = f"{base} {eid}" if eid else base
            sat = block.get("satisfaction", {})
            levels = [
                {"label": lbl, "count": sat.get(lbl, 0), "color": SATISFACTION_COLORS.get(lbl, "#94a3b8")}
                for lbl in SATISFACTION_LABELS
            ]
            items.append({
                "entity_key": key,
                "entity_type": etype,
                "entity_id": eid,
                "entity_label": label,
                "domain": block.get("domain", "hotel"),
                "total": total,
                "positive": block.get("positive", 0),
                "negative": block.get("negative", 0),
                "satisfaction": sat,
                "levels": levels,
            })
        items.sort(key=lambda x: -x["total"])
        return items

    @classmethod
    def _domain_satisfaction_breakdown(cls, store: ReviewStore) -> list[dict[str, Any]]:
        """Domain bazlı memnuniyet dağılımı."""
        from app.services.ontology_service import OntologyService

        raw = store.domain_absa_summary()
        if not raw:
            return []

        domain_labels = {d["id"]: d["label"] for d in OntologyService.list_domains()}
        items: list[dict[str, Any]] = []
        for domain_id, block in raw.items():
            total = block.get("total", 0)
            if total == 0:
                continue
            sat = block.get("satisfaction", {})
            levels = [
                {"label": lbl, "count": sat.get(lbl, 0), "color": SATISFACTION_COLORS.get(lbl, "#94a3b8")}
                for lbl in SATISFACTION_LABELS
            ]
            items.append({
                "domain": domain_id,
                "domain_label": block.get("domain_label") or domain_labels.get(domain_id, domain_id),
                "total": total,
                "positive": block.get("positive", 0),
                "negative": block.get("negative", 0),
                "satisfaction": sat,
                "levels": levels,
            })
        items.sort(key=lambda x: -x["total"])
        return items

    @classmethod
    def top_negative_keywords(
        cls,
        reviews: Optional[list[StoredReview]] = None,
        category: Optional[str] = None,
        limit: int = 10,
        store: Optional[ReviewStore] = None,
        role: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        items = reviews if reviews is not None else cls._reviews(store, role)
        kw_counter: Counter = Counter()
        for r in items:
            if r.sentiment != "Negative":
                continue
            if category and category not in r.category:
                continue
            kw_counter.update(r.keywords)
        return [{"keyword": k, "count": c} for k, c in kw_counter.most_common(limit)]

    @classmethod
    def compute_trends(cls, reviews: list[StoredReview], days: int = 7) -> list[dict[str, Any]]:
        """Son N gün ile önceki N günü karşılaştırır."""
        now = datetime.now(timezone.utc)
        recent_start = now - timedelta(days=days)
        prior_start = now - timedelta(days=days * 2)

        recent_neg: Counter = Counter()
        prior_neg: Counter = Counter()
        recent_total: Counter = Counter()
        prior_total: Counter = Counter()

        for r in reviews:
            dt = cls._parse_dt(r.created_at)
            if not dt:
                continue
            cat = r.category
            if dt >= recent_start:
                recent_total[cat] += 1
                if r.sentiment == "Negative":
                    recent_neg[cat] += 1
            elif dt >= prior_start:
                prior_total[cat] += 1
                if r.sentiment == "Negative":
                    prior_neg[cat] += 1

        trends = []
        for cat in set(list(recent_total.keys()) + list(prior_total.keys())):
            r_neg, p_neg = recent_neg[cat], prior_neg[cat]
            r_tot, p_tot = recent_total[cat], prior_total[cat]
            if r_tot == 0 and p_tot == 0:
                continue
            r_rate = round(r_neg / r_tot * 100, 1) if r_tot else 0
            p_rate = round(p_neg / p_tot * 100, 1) if p_tot else 0
            if p_neg == 0:
                change_pct = 100.0 if r_neg > 0 else 0.0
            else:
                change_pct = round((r_neg - p_neg) / p_neg * 100, 1)
            short = CATEGORY_SHORT.get(cat, cat.split("&")[0].strip())
            trends.append({
                "department": cat,
                "short_name": short,
                "recent_negative": r_neg,
                "prior_negative": p_neg,
                "recent_total": r_tot,
                "prior_total": p_tot,
                "recent_negative_rate_pct": r_rate,
                "change_pct": change_pct,
                "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            })
        trends.sort(key=lambda x: -abs(x["change_pct"]))
        return trends

    @classmethod
    def department_recommendations(cls, store: Optional[ReviewStore] = None, limit: int = 8, role: Optional[str] = None) -> list[dict[str, Any]]:
        """Departman bazlı öncelikli aksiyon önerileri (olumsuz yorumlardan)."""
        reviews = cls._reviews(store, role)
        dept_issues: dict[str, list[StoredReview]] = defaultdict(list)
        for r in reviews:
            if r.sentiment == "Negative":
                dept_issues[r.category].append(r)

        recs: list[dict[str, Any]] = []
        for dept, items in sorted(dept_issues.items(), key=lambda x: -len(x[1])):
            sug_counter = Counter(i.suggestion for i in items if i.suggestion)
            top_sug = sug_counter.most_common(1)[0][0] if sug_counter else "Departman müdürü geri bildirimleri değerlendirmeli."
            kw = Counter()
            for i in items:
                kw.update(i.keywords)
            recs.append({
                "department": dept,
                "issue_count": len(items),
                "priority": "critical" if len(items) >= 8 else "high" if len(items) >= 4 else "medium",
                "top_keywords": [k for k, _ in kw.most_common(5)],
                "recommendation": top_sug,
                "sample_comments": [i.comment[:120] for i in items[:3]],
            })
            if len(recs) >= limit:
                break
        return recs

    @classmethod
    def executive_summary(cls, store: Optional[ReviewStore] = None, role: Optional[str] = None) -> str:
        """Türkçe yönetici özet metni."""
        stats = cls.compute_stats(store, role)
        total = stats["total"]
        if total == 0:
            return "Henüz analiz edilmiş yorum bulunmuyor. Demo verileri yüklemek için /dashboard/seed endpoint'ini çağırın."

        sent = stats["sentiment"]
        cats = stats["category_distribution"]
        top_kw = stats["top_negative_keywords"][:5] or stats["top_keywords"][:5]
        recs = cls.department_recommendations(store, limit=3, role=role)
        trends = stats.get("trends", [])
        pos_rates = stats.get("category_positive_rates", [])

        top_dept = cats[0]["department"] if cats else "—"
        top_dept_count = cats[0]["count"] if cats else 0
        kw_text = ", ".join(k["keyword"] for k in top_kw) if top_kw else "—"

        lines = [
            f"Son {total} misafir yorumu analiz edildi.",
            f"Olumsuz duygu oranı %{sent['negative_pct']}, olumlu oran %{sent['positive_pct']}.",
        ]
        for t in trends[:2]:
            if t["recent_negative"] or t["prior_negative"]:
                verb = "arttı" if t["direction"] == "up" else "azaldı" if t["direction"] == "down" else "değişmedi"
                lines.append(
                    f"Son 7 günde {t['short_name']} şikayetleri %{abs(t['change_pct'])} {verb} "
                    f"({t['prior_negative']} → {t['recent_negative']} olumsuz)."
                )
        if top_kw:
            lines.append(f"En çok geçen negatif kelimeler: {kw_text}.")
        if pos_rates:
            rate_parts = [f"{r['short_name']} kategorisinde olumlu yorum oranı %{r['positive_pct']}" for r in pos_rates[:3]]
            lines.append("; ".join(rate_parts) + ".")
        if stats.get("avg_rating"):
            lines.append(f"Ortalama misafir puanı: {stats['avg_rating']}/5.")
        lines.append(f"En yoğun departman/kategori: {top_dept} ({top_dept_count} yorum, %{cats[0]['pct'] if cats else 0}).")
        if stats.get("mixed_review_count"):
            lines.append(f"{stats['mixed_review_count']} karışık yorum (hem övgü hem şikayet) tespit edildi.")
        if stats.get("manipulation_count"):
            lines.append(f"{stats['manipulation_count']} olası sahte puan/manipülasyon işaretlendi.")

        if recs:
            lines.append("Öncelikli departman aksiyonları:")
            for i, rec in enumerate(recs, 1):
                lines.append(
                    f"  {i}. {rec['department']} ({rec['issue_count']} olumsuz): {rec['recommendation'][:180]}"
                )
        else:
            lines.append("Kritik departman aksiyonu gerektiren yoğun olumsuz yorum kümesi tespit edilmedi.")

        neg_pct = sent["negative_pct"]
        if neg_pct >= 40:
            lines.append("Genel değerlendirme: Olumsuz yorum oranı yüksek — acil iyileştirme planı önerilir.")
        elif neg_pct >= 25:
            lines.append("Genel değerlendirme: Orta düzey memnuniyetsizlik — departman bazlı takip gerekli.")
        else:
            lines.append("Genel değerlendirme: Memnuniyet oranı kabul edilebilir düzeyde; olumsuz kümeleri izlemeye devam edin.")

        return "\n".join(lines)

    @classmethod
    def chatbot_stats(cls) -> dict[str, Any]:
        """RAG chatbot indeks istatistiklerini dashboard ile birleştir."""
        info = RagService.get_index_info()
        return {
            "indexed_records": info.get("indexed_records", 0),
            "index_path": info.get("index_path", ""),
            "data_source": info.get("data_source", ""),
            "mode": info.get("mode", "local"),
            "status": "ready" if info.get("indexed_records") else "missing",
        }

    @classmethod
    def chatbot_analytics_answer(cls, query: str, role: Optional[str] = None) -> Optional[str]:
        """Yönetici istatistik sorularına depo tabanlı cevap."""
        q = query.lower()
        triggers = (
            "istatistik", "oran", "yüzde", "şikayet", "trend", "son 7", "kaç",
            "departman", "olumlu", "olumsuz", "negatif", "kelime", "öneri",
            "rapor", "dashboard", "temizlik", "yemek", "personel", "housekeeping",
            "memnuniyet", "birim", "absa",
        )
        if not any(t in q for t in triggers):
            return None

        store = get_review_store()
        stats = cls.compute_stats(store, role)
        if stats["total"] == 0:
            return (
                "📊 Henüz depolanmış analiz yorumu yok.\n"
                "Yönetici Dashboard sekmesinden demo verileri yükleyin veya yorum analiz edin."
            )

        lines = ["📊 **Yönetici İstatistik Raporu**", ""]
        sent = stats["sentiment"]
        lines.append(f"- Toplam yorum: **{stats['total']}**")
        lines.append(f"- Olumsuz oran: **%{sent['negative_pct']}** | Olumlu: **%{sent['positive_pct']}**")

        for t in stats.get("trends", [])[:3]:
            if t["recent_negative"] or t["prior_negative"]:
                verb = "arttı" if t["direction"] == "up" else "azaldı" if t["direction"] == "down" else "sabit"
                lines.append(f"- Son 7 günde **{t['short_name']}** şikayetleri %{abs(t['change_pct'])} {verb}.")

        neg_kw = stats.get("top_negative_keywords", [])[:5]
        if neg_kw:
            lines.append(f"- En çok geçen negatif kelimeler: **{', '.join(k['keyword'] for k in neg_kw)}**.")

        for r in stats.get("category_positive_rates", [])[:3]:
            lines.append(f"- {r['short_name'].capitalize()} kategorisinde olumlu yorum oranı **%{r['positive_pct']}**.")

        sat_breakdown = stats.get("department_satisfaction_breakdown", [])
        if sat_breakdown:
            lines.append("")
            lines.append("**Birim bazlı memnuniyet dağılımı (ABSA):**")
            for item in sat_breakdown[:4]:
                sat = item.get("satisfaction", {})
                parts = [f"{label}: {sat.get(label, 0)}" for label in SATISFACTION_LABELS if sat.get(label, 0)]
                if parts:
                    short = item.get("short_name", item["department"])
                    lines.append(f"- **{short}**: {', '.join(parts)}")

        recs = cls.department_recommendations(store, limit=2, role=role)
        if recs:
            lines.append("")
            lines.append("**Departman önerileri:**")
            for rec in recs:
                lines.append(f"- {rec['department']}: {rec['recommendation'][:160]}")

        return "\n".join(lines)

    @classmethod
    def full_dashboard(
        cls,
        store: Optional[ReviewStore] = None,
        role: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> dict[str, Any]:
        st = store or get_review_store()
        return {
            "role": role,
            "domain": domain,
            "stats": cls.compute_stats(st, role, domain),
            "recommendations": cls.department_recommendations(st, role=role),
            "executive_summary": cls.executive_summary(st, role),
            "chatbot": cls.chatbot_stats(),
            "review_count": len(cls._reviews(st, role)),
            "available_domains": [{"id": d["id"], "label": d["label"]} for d in __import__(
                "app.services.ontology_service", fromlist=["OntologyService"]
            ).OntologyService.list_domains()],
        }
