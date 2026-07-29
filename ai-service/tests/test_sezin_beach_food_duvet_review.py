# -*- coding: utf-8 -*-
"""Regression: Sezin beach / food taste fail / duvet / guest-info sheet review."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.ontology.engine import reload_hotel_ontology_engine
from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import reload_ontology
from app.services.suggestion_engine import SuggestionContext, build_suggestion
from app.services.turkish_nlp_utils import CAT_FINANCE, CAT_RECEPTION, detect_strong_sentiment


SEZIN_REVIEW = (
    "Personel güler yüzlü.\n"
    "Her ne kadar denize sıfır dense de, odalardan plaja en az 5 dk. yürümek gerekiyor.\n"
    "Yemek çeşidi bol, lezzette sınıfta kalabilir.\n"
    "İçecekler bol ve çeşitli.\n"
    "Yemek salonu yemekhaneden hallice. Bu kadar büyük bir otelde, yemek için dış mekan yetersizdi.\n"
    "Sezin başı olduğu için sanırım, eksiklikler vardı...\n"
    "Odamızda bilgilendirme kağıdı yoktu...mesela telefon numaraları. "
    "Gece üşüyüp yorgana ihtiyaç duyduğumuzda, nereyi aramamız gerektiğini bilemeyip, "
    "incecik pikenin altındactitreyerek uyumaya çalıştık. "
    "Bazı arkadaşlar odalarında yorgan olması sebebiyle şanslıydı..."
)


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()
    reload_hotel_ontology_engine()
    yield


def _find(aspects, *needles: str):
    low_needles = [n.lower() for n in needles]
    return [
        a for a in aspects
        if any(n in (a.clause or "").lower() for n in low_needles)
    ]


class TestSezinClausePipeline:
    def test_icecekler_bol_cesitli_positive_drink(self):
        d = classify_clause("İçecekler bol ve çeşitli.")
        assert d.aspect_key == "drink_variety"
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0
        assert "finans" not in (d.department_label or "").lower()

    def test_sinifta_kalabilir_taste_negative(self):
        d = classify_clause("Yemek çeşidi bol, lezzette sınıfta kalabilir.")
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert d.aspect_key in ("food_taste", "menu_variety", "dining_ambiance")

    def test_hallice_dining_negative(self):
        d = classify_clause("Yemek salonu yemekhaneden hallice.")
        assert d.aspect_key == "dining_ambiance"
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_beach_walk_not_fb_queue(self):
        clause = (
            "Her ne kadar denize sıfır dense de, odalardan plaja en az 5 dk. yürümek gerekiyor."
        )
        d = classify_clause(clause)
        assert d.aspect_key == "beach"
        assert d.aspect_key != "service_queue"
        assert "restoran" not in (d.department_label or "").lower()
        assert d.sentiment == "Negative"

    def test_bilgilendirme_guest_info_not_finance_or_staff_praise(self):
        d = classify_clause("Odamızda bilgilendirme kağıdı yoktu")
        assert d.aspect_key == "guest_info"
        assert d.sentiment == "Negative"
        assert "personel" not in (d.department_label or "").lower()
        sug = build_suggestion(
            SuggestionContext(
                category=CAT_RECEPTION,
                text="Odamızda bilgilendirme kağıdı yoktu",
                keywords=[],
                sentiment="Negative",
            )
        )
        assert "finans" not in sug.lower()
        assert "fatura" not in sug.lower()

    def test_telefon_numaralari_not_on_numara_positive(self):
        sent, score = detect_strong_sentiment("mesela telefon numaraları")
        assert sent != "Positive" or score < 0.3
        d = classify_clause("mesela telefon numaraları")
        assert d.sentiment == "Negative"
        assert d.aspect_key == "guest_info"
        assert "personel" not in (d.department_label or "").lower()

    def test_yorgan_pike_bedding_negative(self):
        d = classify_clause(
            "Gece üşüyüp yorgana ihtiyaç duyduğumuzda, nereyi aramamız gerektiğini bilemeyip, "
            "incecik pikenin altındactitreyerek uyumaya çalıştık"
        )
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        low = (d.department_label or "").lower()
        assert "temizlik" in low or "housekeeping" in low or "oda" in low

    def test_yorgan_sansli_inconsistency_negative(self):
        d = classify_clause(
            "Bazı arkadaşlar odalarında yorgan olması sebebiyle şanslıydı"
        )
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_personel_guler_yuzlu_still_positive(self):
        d = classify_clause("Personel güler yüzlü.")
        assert d.aspect_key == "staff_behavior"
        assert d.sentiment == "Positive"

    def test_finance_category_distinct_from_reception(self):
        assert CAT_FINANCE != CAT_RECEPTION
        assert "muhasebe" in CAT_FINANCE.lower() or "finans" in CAT_FINANCE.lower()


class TestSezinSegmentation:
    def test_dk_period_does_not_orphan_yurumek(self):
        parts = split_clauses_absa(SEZIN_REVIEW)
        joined = " | ".join(p.lower() for p in parts)
        assert "plaja" in joined and "yürümek" in joined
        # beach walk should stay one clause (not split after dk.)
        beachish = [p for p in parts if "plaja" in p.lower() or "denize" in p.lower()]
        assert beachish
        assert any("yürümek" in p.lower() or "yurumek" in p.lower() for p in beachish)


class TestSezinFullReview:
    def test_overall_mixed_not_olumlu_neutral(self):
        result = AbsaService.analyze_multidomain(SEZIN_REVIEW)
        assert result.overall_sentiment == "Mixed"
        assert -0.5 <= (result.overall_score or 0) <= 0.35

    def test_key_routing(self):
        result = AbsaService.analyze_multidomain(SEZIN_REVIEW)

        drinks = _find(result.aspects, "içecekler bol", "icecekler bol")
        assert drinks
        for a in drinks:
            assert a.sentiment == "Positive"
            assert (getattr(a, "aspect_key", None) or a.aspect or "") in (
                "drink_variety", "drink_quality", "food_quality"
            )

        taste = _find(result.aspects, "sınıfta", "sinifta")
        assert taste
        for a in taste:
            assert a.sentiment == "Negative"

        hallice = _find(result.aspects, "hallice", "yemekhane")
        assert hallice
        for a in hallice:
            assert a.sentiment == "Negative"

        beach = _find(result.aspects, "plaja", "denize sıfır", "denize sifir")
        assert beach
        for a in beach:
            ak = (getattr(a, "aspect_key", None) or a.aspect or "").lower()
            assert "queue" not in ak and "kuyruk" not in ak
            dept = (a.department_label or "").lower()
            assert "restoran" not in dept or "plaj" in dept or "rekreasyon" in dept or "çevre" in dept
            assert a.sentiment == "Negative"

        info = _find(result.aspects, "bilgilendirme", "telefon numar")
        assert info
        for a in info:
            assert a.sentiment == "Negative"
            dept = (a.department_label or "").lower()
            assert "personel" not in dept
            sug = (a.suggestion or "").lower()
            assert "finans" not in sug and "fatura" not in sug

        bedding = _find(result.aspects, "yorgan", "pike", "üşüyü", "usuyu")
        assert bedding
        for a in bedding:
            assert a.sentiment == "Negative"

        staff = _find(result.aspects, "güler yüzlü", "guler yuzlu")
        assert staff
        for a in staff:
            assert a.sentiment == "Positive"
