"""Regression: Ultra AIH bar/queue multi-complaint review (systemic ABSA).

User corrections (not Crystal-specific if/else):
- Primary category F&B/queue (not Spa + klor aksiyon)
- Drink wait → Servis/Kuyruk (not İçecek Kalitesi)
- Şezlong sıra → Havuz / Aktivite (not F&B)
- Aktiviteler → Animasyon (not Spa water quality)
- Ses yalıtımı → Oda ses/konfor
- Sarcasm distance / diye tuttuk / çarçur / Türkçe bilmiyor → Negative
- 18.00-24.00 must not split on dots
- Summary operational (not mid-cropped "dakika sıra…")
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.category_rules import classify_by_rules
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.keyword_service import KeywordService
from app.services.ontology_service import reload_ontology
from app.services.rag_service import RagService
from app.services.sentiment_service import SentimentService
from app.services.suggestion_engine import SuggestionContext, build_suggestion
from app.services.turkish_nlp_utils import (
    CAT_FOOD,
    CAT_SPA,
    detect_strong_sentiment,
)

ULTRA_QUEUE_REVIEW = (
    "Otelde yoğun bir sıra mevcut. Herhangi bir içecek için bile 15 20 dakika sıra bekleniyor.\n"
    "Odaların ses yalıtımı çok kötü yan odadaki adamın telefonu çalıyor sanki bizim oda da. "
    "Yemek konusunda iyi bir otel ama onun dışında güzel bir yanı yok. "
    "Oda otelin bir ucunda havuz bir ucunda 500 metre yürümek veya koşmak isterseniz güzel. "
    "Otel çalışanlarının bazıları Türkçe bile bilmiyor. "
    "Havuz başında şezlong bulunmuyor bulmaya çalıştığımızda onun için bile sıraya girmeniz gerekiyor. "
    "Bayram nedeniyle aktiviteler kaldırılmış. Yani bir masa tenisi masası ne kadar yer kaplayabilir ki. "
    "WiFi ye asla bağlanılamıyor. "
    "Konsept adı altına belli çeşit alkoller sadece belli barlarda var. "
    "Ultra herşey dahil olarak 7/24 bar var diye tuttuk ama 7/24 açık olan barda tekila yok "
    "sadece bir barda var. O olan bar 18.00-24.00 arası çalışıyor ama 30-45 dakika arası sıra "
    "beklemeden herhangi bir içecek alınamıyor.\n"
    "Parasını çarçur etmek isteyen varsa tutabilir tabiki."
)


@pytest.fixture(autouse=True)
def _reload():
    reload_ontology()
    reload_pipeline_config()
    yield


class TestClockSegmentation:
    def test_time_range_not_split_on_dot(self):
        parts = split_clauses_absa(
            "O olan bar 18.00-24.00 arası çalışıyor ama 30-45 dakika arası sıra "
            "beklemeden herhangi bir içecek alınamıyor."
        )
        joined = " | ".join(parts)
        assert "18.00-24.00" in joined or "18.00" in joined
        assert not any(
            p.strip().startswith("00") or p.strip() == "00 arası çalışıyor"
            for p in parts
        )
        assert not any(re_match(p) for p in parts)


def re_match(p: str) -> bool:
    """Broken fragment: lone '00 arası…' after time split."""
    t = p.strip().lower()
    return t.startswith("00 ") or t.startswith("00arası") or t == "00"


class TestClauseLevelExpectations:
    def test_drink_wait_is_service_queue_not_drink_quality(self):
        clause = "Herhangi bir içecek için bile 15 20 dakika sıra bekleniyor."
        d = classify_clause(clause)
        assert d.aspect_key == "service_queue"
        assert "kuyruk" in d.aspect_label.lower() or "servis" in d.aspect_label.lower()
        assert "kalite" not in d.aspect_label.lower()
        assert d.sentiment == "Negative"
        assert "restaurant" in d.department_label.lower() or d.category == CAT_FOOD or "yiyecek" in (d.category or "").lower()

    def test_sunbed_queue_is_pool_not_fb(self):
        clause = (
            "Havuz başında şezlong bulunmuyor bulmaya çalıştığımızda "
            "onun için bile sıraya girmeniz gerekiyor."
        )
        d = classify_clause(clause)
        assert d.aspect_key in ("pool_lounger", "pool_queue")
        assert "havuz" in d.aspect_label.lower() or "şezlong" in d.aspect_label.lower() or "aktivite" in d.aspect_label.lower()
        assert "havuz" in d.department_label.lower() or "rekreasyon" in d.department_label.lower()
        assert "restaurant" not in d.department_label.lower()
        assert d.sentiment == "Negative"

    def test_activities_cancelled_is_animation_not_spa(self):
        clause = "Bayram nedeniyle aktiviteler kaldırılmış."
        d = classify_clause(
            clause,
            base_mapping={
                "department": "spa",
                "department_label": "Spa & Wellness",
                "departmentLabel": "Spa & Wellness",
            },
        )
        assert d.aspect_key == "animation"
        assert "spa" not in d.department_label.lower()
        assert "animasyon" in d.department_label.lower() or "rekreasyon" in d.department_label.lower()
        assert "animasyon" in (d.category or "").lower() or "etkinlik" in (d.category or "").lower() or "rekreasyon" in (d.category or "").lower()

    def test_sound_insulation_room_noise(self):
        clause = "Odaların ses yalıtımı çok kötü yan odadaki adamın telefonu çalıyor sanki bizim oda da."
        d = classify_clause(clause)
        assert d.aspect_key == "room_noise"
        assert d.sentiment == "Negative"
        assert "oda" in d.department_label.lower() or "oda" in d.aspect_label.lower()

    def test_distance_sarcasm_negative(self):
        clause = "Oda otelin bir ucunda havuz bir ucunda 500 metre yürümek veya koşmak isterseniz güzel."
        sent, score = detect_strong_sentiment(clause)
        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_staff_turkish_negative(self):
        clause = "Otel çalışanlarının bazıları Türkçe bile bilmiyor."
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.aspect_key == "staff_behavior" or "personel" in d.department_label.lower()

    def test_alcohol_variety_negative(self):
        clause = "Konsept adı altına belli çeşit alkoller sadece belli barlarda var."
        d = classify_clause(clause)
        assert d.aspect_key == "drink_variety"
        assert d.sentiment == "Negative"
        assert "bar" in d.department_label.lower() or "yiyecek" in (d.category or "").lower()

    def test_expectation_mismatch_diye_tuttuk_negative(self):
        clause = "Ultra herşey dahil olarak 7/24 bar var diye tuttuk"
        sent, score = detect_strong_sentiment(clause)
        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.sentiment == "Negative"

    def test_money_waste_carcur_negative(self):
        clause = "Parasını çarçur etmek isteyen varsa tutabilir tabiki."
        sent, score = detect_strong_sentiment(clause)
        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.sentiment == "Negative"
        assert d.aspect_key in ("value_for_money", "guest_experience")


class TestFullReviewRegression:
    def test_primary_category_food_not_spa(self):
        r = classify_by_rules(ULTRA_QUEUE_REVIEW)
        assert r.category == CAT_FOOD
        assert r.category != CAT_SPA

    def test_suggestion_not_pool_chlorine(self):
        r = classify_by_rules(ULTRA_QUEUE_REVIEW)
        sug = build_suggestion(
            SuggestionContext(
                text=ULTRA_QUEUE_REVIEW,
                category=r.category,
                sentiment="Negative",
                keywords=["sıra", "içecek", "bar"],
                is_mixed=True,
            )
        )
        low = sug.lower()
        assert "klor" not in low and "pH".lower() not in low and "ph değer" not in low
        assert any(w in low for w in ("kuyruk", "f&b", "bar", "servis", "içecek", "animasyon", "şezlong"))

    def test_absa_aspects_cover_user_labels(self):
        result = AbsaService.analyze(ULTRA_QUEUE_REVIEW, rating=None, multidomain=True)
        assert result.aspects

        def find(*needles: str):
            return [
                a for a in result.aspects
                if any(n in a.clause.lower() for n in needles)
            ]

        drink_q = find("15 20", "15-20", "dakika", "içecek", "icecek")
        assert drink_q
        assert any(
            "kuyruk" in (a.aspect_label or a.aspect or "").lower()
            or "servis" in (a.aspect_label or a.aspect or "").lower()
            or "sıra" in (a.aspect_label or a.aspect or "").lower()
            or getattr(a, "aspect_key", "") in ("service_queue", "queue_waiting", "drink_quality")
            for a in drink_q
        )
        assert all("kalite" not in (a.aspect_label or a.aspect or "").lower() for a in drink_q)

        sez = find("şezlong", "sezlong")
        assert sez
        for a in sez:
            label = (getattr(a, "department_label", None) or a.department or "").lower()
            al = (a.aspect_label or a.aspect or "").lower()
            assert "restaurant" not in label
            assert "havuz" in label or "havuz" in al or "şezlong" in al or "aktivite" in al

        anim = find("aktivite")
        assert anim
        for a in anim:
            label = (getattr(a, "department_label", None) or a.department or "").lower()
            assert "spa" not in label
            assert "animasyon" in label or getattr(a, "aspect_key", "") == "animation"

        noise = find("yalıtım", "yalitim", "yan oda")
        assert noise
        assert any(a.sentiment == "Negative" for a in noise)

        dist = find("500 metre", "isterseniz güzel")
        assert dist
        assert all(a.sentiment == "Negative" for a in dist)
        for a in dist:
            al = (a.aspect_label or a.aspect or "").lower()
            assert "temiz" not in al, f"mesafe sarcasm ≠ havuz temizliği: {a.aspect_label}"

        staff = find("türkçe", "turkce")
        assert staff
        assert all(a.sentiment == "Negative" for a in staff)

        waste = find("çarçur", "carcur")
        assert waste
        assert all(a.sentiment == "Negative" for a in waste)

        wifi = find("wifi", "bağlan")
        assert wifi

    def test_summary_operational_not_orphan_crop(self):
        summary = RagService.generate_summary(ULTRA_QUEUE_REVIEW)
        low = summary.lower().strip()
        assert low
        assert not low.startswith("dakika sıra")
        assert not low.startswith("dakika sira")
        assert any(
            w in low
            for w in ("sıra", "sira", "kuyruk", "bekle", "bar", "içecek", "icecek", "wifi", "yalıtım", "yalitim")
        )
        assert "klor" not in low

    def test_analiz_raporu_top_level_fields(self):
        """AI Analiz Raporu panel fields — same path as /analyze-review."""
        cat = classify_by_rules(ULTRA_QUEUE_REVIEW)
        sentiment, score = SentimentService.analyze_sentiment(ULTRA_QUEUE_REVIEW, None)
        keywords = KeywordService.extract_keywords(ULTRA_QUEUE_REVIEW, max_keywords=6)
        summary = RagService.generate_summary(ULTRA_QUEUE_REVIEW)
        suggestion = build_suggestion(
            SuggestionContext(
                text=ULTRA_QUEUE_REVIEW,
                category=cat.category,
                sentiment=sentiment,
                keywords=keywords,
                is_mixed=cat.is_mixed,
                secondary_category=cat.secondary_category,
            )
        )

        assert cat.category == CAT_FOOD
        assert cat.category != CAT_SPA
        assert cat.is_mixed is True
        assert sentiment in ("Negative", "Neutral")

        kw_joined = " ".join(keywords).lower()
        assert len(keywords) >= 4
        assert all(len(k) >= 3 for k in keywords)
        assert "oteliçecek" not in kw_joined and "oteli" not in kw_joined.replace(" ", "")
        assert any(w in kw_joined for w in ("sira", "sıra", "icecek", "içecek", "bar", "wifi", "sezlong", "şezlong"))

        low_sum = summary.lower()
        assert any(w in low_sum for w in ("sıra", "sira", "bar", "içecek", "icecek", "bekle", "wifi"))
        assert not low_sum.startswith("dakika sıra")

        low_sug = suggestion.lower()
        assert "klor" not in low_sug and "ph değer" not in low_sug
        assert any(w in low_sug for w in ("kuyruk", "bar", "f&b", "servis", "içecek", "icecek"))
