"""Regression: Crystal Family overall POSITIVE review — F&B/pool/FO praise routing."""
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
from app.services.turkish_nlp_utils import CAT_FOOD, CAT_SPA, analyze_mixed_review, normalize_turkish

CRYSTAL_FAMILY_POSITIVE = (
    "1 -3 mayıs arasında konakladığımız otel de giriş resepsiyonda bizi güler yüz ile sezen hanım karşıladı , "
    "Tesis aşırı büyük havuzlar ve özellikle aqua parkları çok eğlenceli "
    "genellikle bizim gibi çocuklu ailelerin tercih ettiğini gördük . "
    "Açık ve kapalı havuzların ısıtmalı olması çok güzel "
    "Yiyecek içecek olarak çeşitleri yeterli kaliteli ve lezzetli, "
    "Pastane ve kahve köşesi çok güzel di. "
    "Özellike türk kahvesi ve yanında ikram edilen kendi üretimleri olan lokum :) "
    "Genel olarak biz otelden mutlu ayrıldık "
    "Lobide tanıştığımız Crystal Family Otel in müdürü Tuncay bey e ayrıca ilgi alaka ve misafirperverliği için çok teşekkür ederiz "
    "Bu yıl yaz tatilinde de tercihimiz Crystal Family olacak"
)


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()
    yield


def _find(aspects, *needles: str):
    low_needles = [normalize_turkish(n.lower()) for n in needles]
    return [
        a for a in aspects
        if any(n in normalize_turkish(a.clause.lower()) for n in low_needles)
    ]


def _is_fb(label: str) -> bool:
    low = (label or "").lower()
    return "f&b" in low or "yiyecek" in low or "restoran" in low


class TestClauseLevelCrystalPositive:
    def test_pastane_fb_not_pool(self):
        d = classify_clause("Pastane ve kahve köşesi çok güzel di.")
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0.3
        assert _is_fb(d.department_label)
        assert "havuz" not in (d.department_label or "").lower()
        assert "rekreasyon" not in (d.department_label or "").lower()

    def test_lokum_positive_not_neutral(self):
        clause = "Özellike türk kahvesi ve yanında ikram edilen kendi üretimleri olan lokum :)"
        d = classify_clause(clause)
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0.3
        assert _is_fb(d.department_label)

    def test_heated_pool_not_ac(self):
        clause = "Açık ve kapalı havuzların ısıtmalı olması çok güzel"
        d = classify_clause(clause)
        assert d.sentiment == "Positive"
        assert d.aspect_key in ("pool_lounger", "pool_queue", "kids_capacity")
        assert "teknik" not in (d.department_label or "").lower()
        assert d.aspect_key != "tech_general"

    def test_food_variety_restaurant_not_bar(self):
        clause = "Yiyecek içecek olarak çeşitleri yeterli kaliteli ve lezzetli,"
        d = classify_clause(clause)
        assert d.sentiment == "Positive"
        assert _is_fb(d.department_label)
        assert "bar" not in (d.department_label or "").lower()

    def test_mutlu_ayrildik_atmosphere_not_hk(self):
        d = classify_clause("Genel olarak biz otelden mutlu ayrıldık")
        assert d.sentiment == "Positive"
        assert d.aspect_key == "guest_experience"
        assert "temizlik" not in (d.department_label or "").lower()
        assert "housekeeping" not in (d.department_label or "").lower()

    def test_manager_thanks_front_office_high(self):
        clause = (
            "Lobide tanıştığımız Crystal Family Otel in müdürü Tuncay bey e ayrıca ilgi alaka "
            "ve misafirperverliği için çok teşekkür ederiz Bu yıl yaz tatilinde de tercihimiz Crystal Family olacak"
        )
        d = classify_clause(clause)
        assert d.sentiment == "Positive"
        assert d.sentiment_score >= 0.65
        assert d.aspect_key == "front_office"
        low = (d.department_label or "").lower()
        assert "büro" in low or "front" in low or "misafir" in low


class TestFullCrystalPositiveReview:
    def test_not_complaint_primary_mixed(self):
        mixed = analyze_mixed_review(CRYSTAL_FAMILY_POSITIVE)
        assert mixed.is_mixed is False
        rules = classify_by_rules(CRYSTAL_FAMILY_POSITIVE)
        assert rules.is_mixed is False

    def test_segmentation_covers_key_topics(self):
        parts = split_clauses_absa(CRYSTAL_FAMILY_POSITIVE)
        joined = " | ".join(p.lower() for p in parts)
        assert len(parts) >= 6
        assert "pastane" in joined or "kahve" in joined
        assert "lokum" in joined
        assert "mutlu ayrild" in joined or "mutlu ayrıl" in joined
        assert "isitmali" in joined or "ısıtmalı" in joined

    def test_absa_no_pool_bleed_on_fb_praise(self):
        result = AbsaService.analyze(CRYSTAL_FAMILY_POSITIVE, rating=5, multidomain=True)
        assert len(result.aspects) >= 6

        for label in ("pastane", "lokum", "turk kahvesi", "türk kahvesi", "yiyecek"):
            matches = _find(result.aspects, label)
            assert matches, f"missing clause for {label}"
            for a in matches:
                dept = (a.department_label or a.department or "").lower()
                assert "havuz" not in dept or "havuz" in a.clause.lower()
                assert "rekreasyon" not in dept or "aquapark" in a.clause.lower() or "havuz" in a.clause.lower()
                if "pastane" in a.clause.lower() or "lokum" in a.clause.lower():
                    assert _is_fb(a.department_label or a.department)
                    assert a.sentiment == "Positive"

        mutlu = _find(result.aspects, "mutlu ayrild", "mutlu ayrıl")
        assert mutlu
        for a in mutlu:
            assert a.sentiment == "Positive"
            assert "temizlik" not in (a.department_label or "").lower()

        heated = _find(result.aspects, "isitmali", "ısıtmalı")
        assert heated
        for a in heated:
            assert a.sentiment == "Positive"
            assert getattr(a, "entity_id", None) != "eq_air_conditioner"
            assert "teknik" not in (a.department_label or "").lower()

        assert result.overall_sentiment == "Positive"
