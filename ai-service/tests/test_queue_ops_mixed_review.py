"""Regression: F&B queue / distance sarcasm / drink variety ops review.

Must NOT classify primary as Spa+chlorine; drink wait = Servis/Kuyruk;
şezlong = Havuz + queue; ses yalıtımı = Odalar; time ranges stay intact.
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
from app.services.ontology_service import reload_ontology
from app.services.rag_service import RagService
from app.services.suggestion_engine import build_suggestion, SuggestionContext
from app.services.turkish_nlp_utils import (
    CAT_FOOD,
    CAT_SPA,
    detect_strong_sentiment,
)

QUEUE_OPS_REVIEW = (
    "Otelde yoğun bir sıra mevcut. Herhangi bir içecek için bile 15 20 dakika sıra bekleniyor. "
    "Odaların ses yalıtımı çok kötü yan odadaki adamın telefonu çalıyor sanki bizim oda da. "
    "Yemek konusunda iyi bir otel ama onun dışında güzel bir yanı yok. "
    "Oda otelin bir ucunda havuz bir ucunda 500 metre yürümek veya koşmak isterseniz güzel. "
    "Otel çalışanlarının bazıları Türkçe bile bilmiyor. "
    "Havuz başında şezlong bulunmuyor bulmaya çalıştığımızda onun için bile sıraya girmeniz gerekiyor. "
    "Bayram nedeniyle aktiviteler kaldırılmış. Yani bir masa tenisi masası ne kadar yer kaplayabilir ki. "
    "WiFi ye asla bağlanılamıyor. "
    "Konsept adı altına belli çeşit alkoller sadece belli barlarda var. "
    "Ultra herşey dahil olarak 7/24 bar var diye tuttuk ama 7/24 açık olan barda tekila yok sadece bir barda var. "
    "O olan bar 18.00-24.00 arası çalışıyor ama 30-45 dakika arası sıra beklemeden herhangi bir içecek alınamıyor. "
    "Parasını çarçur etmek isteyen varsa tutabilir tabiki."
)


@pytest.fixture(autouse=True)
def _reload():
    reload_ontology()
    reload_pipeline_config()
    yield


class TestTimeSplitIntact:
    def test_bar_hours_not_fragmented(self):
        parts = split_clauses_absa(
            "O olan bar 18.00-24.00 arası çalışıyor ama 30-45 dakika arası sıra beklemeden "
            "herhangi bir içecek alınamıyor."
        )
        joined = " | ".join(parts)
        assert "o olan bar 18" not in joined.lower() or "18.00" in joined or "18§00" in joined
        assert not any(p.strip() in ("00 arası çalışıyor", "00 arasi calisiyor") for p in parts)
        assert any("18" in p and "24" in p for p in parts) or any(
            "dakika" in p.lower() and ("sıra" in p.lower() or "sira" in p.lower()) for p in parts
        )
        # Must not invent orphan "00 arası çalışıyor"
        assert not any(p.strip().startswith("00") for p in parts)


class TestAspectSentimentCorrections:
    def test_drink_wait_is_service_queue_not_drink_quality(self):
        d = classify_clause("Herhangi bir içecek için bile 15 20 dakika sıra bekleniyor")
        assert d.aspect_key in ("queue_waiting", "service_queue")
        assert "kuyruk" in d.aspect_label.lower() or "servis" in d.aspect_label.lower() or "sıra" in d.aspect_label.lower()
        assert d.sentiment == "Negative"
        assert "kalite" not in d.aspect_label.lower()

    def test_sezlong_queue_is_pool_not_fb(self):
        d = classify_clause(
            "Havuz başında şezlong bulunmuyor bulmaya çalıştığımızda onun için bile sıraya girmeniz gerekiyor"
        )
        assert d.aspect_key in ("queue_waiting", "pool", "pool_lounger", "service_queue", "pool_queue")
        assert "havuz" in d.department_label.lower() or "rekreasyon" in d.department_label.lower()
        assert "restaurant" not in d.department_label.lower()
        assert d.sentiment == "Negative"

    def test_sound_insulation_is_room_noise(self):
        d = classify_clause(
            "Odaların ses yalıtımı çok kötü yan odadaki adamın telefonu çalıyor sanki bizim oda da"
        )
        assert d.aspect_key in ("soundproofing", "room_noise")
        assert "housekeeping" in d.department.lower() or "oda" in d.department_label.lower()
        assert "temizlik" not in d.aspect_label.lower()
        assert d.sentiment == "Negative"

    def test_tequila_variety_negative(self):
        d = classify_clause("7/24 açık olan barda tekila yok sadece bir barda var")
        assert d.aspect_key in ("drink_quality", "drink_variety", "menu_variety")
        assert "f&b" in d.department_label.lower() or "yiyecek" in d.department_label.lower() or "bar" in d.department_label.lower()
        assert d.sentiment == "Negative"

    def test_alcohol_concept_variety(self):
        d = classify_clause("Konsept adı altına belli çeşit alkoller sadece belli barlarda var")
        assert d.aspect_key in ("drink_quality", "drink_variety", "menu_variety")
        assert d.sentiment == "Negative"

    def test_distance_sarcasm_negative(self):
        sent, score = detect_strong_sentiment(
            "Oda otelin bir ucunda havuz bir ucunda 500 metre yürümek veya koşmak isterseniz güzel"
        )
        assert sent == "Negative"
        d = classify_clause(
            "Oda otelin bir ucunda havuz bir ucunda 500 metre yürümek veya koşmak isterseniz güzel",
            base_sentiment=sent,
            base_score=score,
        )
        assert d.sentiment == "Negative"

    def test_724_disappointment_negative(self):
        d = classify_clause("Ultra herşey dahil olarak 7/24 bar var diye tuttuk")
        assert d.sentiment == "Negative"

    def test_staff_turkish_negative(self):
        d = classify_clause("Otel çalışanlarının bazıları Türkçe bile bilmiyor")
        assert d.aspect_key in ("communication", "staff_attitude", "staff_behavior")
        assert d.sentiment == "Negative"

    def test_money_waste_negative(self):
        d = classify_clause("Parasını çarçur etmek isteyen varsa tutabilir tabiki.")
        assert d.sentiment == "Negative"
        assert d.aspect_key in ("price_value", "value_for_money", "guest_experience", "general_atmosphere")

    def test_animation_not_spa_wellness_water(self):
        d = classify_clause("Bayram nedeniyle aktiviteler kaldırılmış")
        assert d.aspect_key in ("animation", "pool")
        assert "rekreasyon" in d.department_label.lower() or "animasyon" in d.department_label.lower() or "leisure" in d.department_key.lower()


class TestCategorySummarySuggestion:
    def test_primary_not_spa_chlorine(self):
        r = classify_by_rules(QUEUE_OPS_REVIEW)
        assert r.category != CAT_SPA or "Yiyecek" in r.category or "yemek" in r.category.lower()
        # Prefer F&B / Genel ops over Spa wellness
        assert r.category == CAT_FOOD or r.category != CAT_SPA

    def test_summary_not_truncated_junk(self):
        summary = RagService.generate_summary(QUEUE_OPS_REVIEW)
        low = summary.lower()
        assert summary.strip() != "dakika sıra bekleniyor."
        assert not low.startswith("dakika sıra")
        assert any(w in low for w in ("sıra", "sira", "kuyruk", "bekle", "içecek", "icecek", "şezlong", "sezlong"))
        assert len(summary.split()) >= 5

    def test_suggestion_matches_dominant_queue_not_chlorine(self):
        sug = build_suggestion(
            SuggestionContext(
                category=CAT_SPA,  # wrong category on purpose
                text=QUEUE_OPS_REVIEW,
                keywords=["sıra", "içecek", "şezlong"],
                sentiment="Negative",
            )
        )
        low = sug.lower()
        assert "klor" not in low and "ph" not in low and "pH".lower() not in low
        assert any(w in low for w in ("kuyruk", "servis", "bar", "şezlong", "sezlong", "f&b", "içecek"))


class TestFullAbsaRegression:
    def test_absa_key_corrections(self):
        result = AbsaService.analyze(QUEUE_OPS_REVIEW, rating=None, multidomain=True)
        clauses = [a.clause.lower() for a in result.aspects]

        # Time fragments must not leak
        assert not any(c.strip().startswith("00") for c in clauses)

        drink_wait = [
            a for a in result.aspects
            if ("içecek" in a.clause.lower() or "icecek" in a.clause.lower())
            and any(w in a.clause.lower() for w in ("dakika", "sıra", "sira", "bekle"))
        ]
        assert drink_wait
        for a in drink_wait:
            al = (a.aspect_label or a.aspect or "").lower()
            assert "kalite" not in al
            assert "servis" in al or "kuyruk" in al or "sıra" in al or a.aspect_key in ("queue_waiting", "service_queue")

        noise = [a for a in result.aspects if "yalıt" in a.clause.lower() or "yalit" in a.clause.lower()]
        assert noise
        for a in noise:
            assert a.department in ("housekeeping", "rooms") or a.aspect_key in ("soundproofing", "room_noise")
            assert "temizlik" not in (a.aspect_label or "").lower()
            assert a.sentiment == "Negative"

        sez = [a for a in result.aspects if "şezlong" in a.clause.lower() or "sezlong" in a.clause.lower()]
        assert sez
        for a in sez:
            assert "restaurant" not in (a.department_label or "").lower()
            assert a.sentiment == "Negative"
            assert a.aspect_key in ("pool", "pool_queue", "pool_lounger", "queue_waiting", "service_queue") or (
                "servis" in (a.aspect_label or "").lower() or "şezlong" in (a.aspect_label or "").lower() or "havuz" in (a.aspect_label or "").lower()
            )

        wifi = [a for a in result.aspects if "wifi" in a.clause.lower()]
        assert wifi
        for a in wifi:
            al = (a.aspect_label or a.aspect or "").lower()
            assert "klima" not in al
            assert a.sentiment == "Negative"

        dist = [a for a in result.aspects if "500" in a.clause or "metre" in a.clause.lower()]
        assert dist
        assert any(a.sentiment == "Negative" for a in dist)

        waste = [a for a in result.aspects if "çarçur" in a.clause.lower() or "carcur" in a.clause.lower()]
        assert waste
        assert all(a.sentiment == "Negative" for a in waste)

        staff = [a for a in result.aspects if "türkçe" in a.clause.lower() or "turkce" in a.clause.lower()]
        assert staff
        assert all(a.sentiment == "Negative" for a in staff)
