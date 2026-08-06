"""Regression: long negative operational overload resort review (Eren YALÇINKAYA).

Systemic fixes — NOT Crystal if/else:
- Mega-clause split: food queue / alacarte / pool sunbed / bar staffing / ops
- No Havuz bleed on food taste, elevator trash, security, dirty F&B service
- Operations frame: kapasite, organizasyon, işletme, işleyiş
- Security: sap adam, yan göz, pis hissettiriyor
- Sarcasm: komik kaçıyor, aldanmayın → Negative
- Churros → F&B availability (not staff)
- Koridor bardak → HK public area
- Elevator trash → HK/engineering (not pool/spa)
- paramıza oldu / ingilizce / azarlar → Negative
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
from app.services.suggestion_engine import SuggestionContext, build_suggestion
from app.services.turkish_nlp_utils import CAT_FOOD, CAT_SPA, CAT_STAFF, detect_strong_sentiment

OPS_OVERLOAD_REVIEW = (
    "5 yıldızlı yorumlara aldanmayın. Otel kapasitesine ulaşmadıklarını söylemelerine rağmen "
    "15 metre yemek kuyrukları a la carte için 1 buçuk saat yemek beklemek havuzda şezlong "
    "bulamamak ve bu kalabalığa rağmen barda 1 2 çalışanın olması bizim her bara gittiğimizde "
    "1 saat beklememiz oteldeki operasyon ekibinin ve organizasyonun ne kadar zayıf olduğunu gösteriyor. "
    "Yemekte servis bekliyoruz kirli servis getiriyorlar ve gelmesi de yine 10 15 dk sürüyor. "
    "Çalışanların çoğu yabancı ve ingilizce dahi anlamıyorlar. "
    "Otelde herkes bıkmış kimse sevmiyor ve bunalmışlar. "
    "Otelde sap adam grupları var yaşlı başlı tipler ve buna rağmen kadın erkek farketmeksizin "
    "herkese yan gözle bakıyorlar ve çok pis hissettiriyorlar aşırı rahatsız ediciler. "
    "Aile oteli demişlerdi ve buna uygun tek bir şey görmedim bu adamları otelde barındırıp da "
    "aile oteli denmesi komik kaçıyor. "
    "Bir tane churrosu 5 günde yiyemedik her gittiğimizde bugün yok yarın yapılır dediler yine yoktu. "
    "Bir de azarlar gibi konuşup insanı geriyorlar. "
    "Koridorlarda kokteyl bardakları vs 2 3 gün durdu cidden gözlerime inanamadım pis bardakları bırakmışlar orada. "
    "Sabahın köründe oda temizliği geliyor kapıyı çalmadan direkt kapıyı açıyorlar şok oldum yani "
    "belki üstümüz müsait değil öyle çalmadan etmeden odaya dalıyorlar sabahın köründe. "
    "Asansörde de yine 3 gün her gün art arda biriken çöp gördüm 3 günün sonunda temizlemişler. "
    "Yemeklerde cidden lezzet yok hem kuş kadar yapıyorlar kimseye yetmiyor hem de tatları kötü "
    "yani tat alma duyumu kaybettim sandım her şeyin tadı birbirine benziyor garip baya. "
    "Çalışan sayısı aşırı aşırı az yetişemiyorlar insanların canları çıkmış ve bu sefer onlar da mağdur oluyor. "
    "İşletme cidden kötü yönetiyor alan güzel otel büyük ama işleyiş cidden kötü. "
    "Bir daha tercih edeceğimizi asla düşünmüyorum. Olan paramıza ve zamanımıza oldu. Eren YALÇINKAYA"
)


@pytest.fixture(autouse=True)
def _reload():
    reload_ontology()
    reload_pipeline_config()
    yield


def _find(aspects, *needles: str):
    low_needles = [n.lower() for n in needles]
    return [
        a for a in aspects
        if any(n in a.clause.lower() for n in low_needles)
    ]


class TestSegmentation:
    def test_mega_clause_splits_on_topic_boundaries(self):
        parts = split_clauses_absa(OPS_OVERLOAD_REVIEW)
        joined = " | ".join(p.lower() for p in parts)
        assert "yemek beklemek" in joined
        assert "havuzda" in joined or "şezlong" in joined or "sezlong" in joined
        assert not any(
            p.lower().count("yemek beklemek") and p.lower().count("asansörde")
            for p in parts
        )
        food_only = [p for p in parts if "lezzet" in p.lower() and "asansör" not in p.lower()]
        elev_only = [p for p in parts if "asansör" in p.lower() and "lezzet" not in p.lower()]
        assert food_only
        assert elev_only


class TestClauseLevelExpectations:
    def test_alanmayin_negative_meta(self):
        d = classify_clause("5 yıldızlı yorumlara aldanmayın")
        assert d.sentiment == "Negative"

    def test_english_language_negative(self):
        clause = "Çalışanların çoğu yabancı ve ingilizce dahi anlamıyorlar."
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.aspect_key == "staff_behavior"
        assert "personel" in d.department_label.lower()

    def test_security_sap_adam_not_pool(self):
        clause = (
            "Otelde sap adam grupları var yaşlı başlı tipler ve buna rağmen kadın erkek "
            "farketmeksizin herkese yan gözle bakıyorlar ve çok pis hissettiriyorlar aşırı rahatsız ediciler."
        )
        d = classify_clause(clause, frame_context={"pool": True, "aquapark": True})
        assert d.aspect_key == "safety"
        assert d.sentiment == "Negative"
        assert "havuz" not in d.department_label.lower()
        assert "spa" not in d.department_label.lower()

    def test_aile_oteli_sarcasm_negative_not_hk_positive(self):
        clause = (
            "Aile oteli demişlerdi ve buna uygun tek bir şey görmedim bu adamları otelde barındırıp da "
            "aile oteli denmesi komik kaçıyor."
        )
        sent, score = detect_strong_sentiment(clause)
        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.sentiment == "Negative"
        assert d.aspect_key in ("guest_experience", "general")
        assert "temizlik" not in (d.aspect_label or "").lower()

    def test_churros_food_availability_not_staff(self):
        clause = "Bir tane churrosu 5 günde yiyemedik her gittiğimizde bugün yok yarın yapılır dediler yine yoktu."
        d = classify_clause(clause)
        assert d.aspect_key == "food_availability"
        assert "f&b" in d.department_label.lower() or "yiyecek" in d.category.lower()
        assert d.sentiment == "Negative"

    def test_koridor_glasses_hk_public_area(self):
        clause = (
            "Koridorlarda kokteyl bardakları vs 2 3 gün durdu cidden gözlerime inanamadım "
            "pis bardakları bırakmışlar orada."
        )
        d = classify_clause(clause, frame_context={"pool": True})
        assert d.aspect_key == "housekeeping_service"
        assert d.sentiment == "Negative"
        assert "havuz" not in d.aspect_label.lower()

    def test_elevator_trash_not_pool_or_food(self):
        clause = "Asansörde de yine 3 gün her gün art arda biriken çöp gördüm 3 günün sonunda temizlemişler."
        d = classify_clause(clause, frame_context={"pool": True, "fb": True})
        assert d.aspect_key == "elevator_cleanliness"
        assert d.aspect_key not in ("pool_lounger", "pool_queue", "food_taste")
        assert "havuz" not in (d.aspect_label or "").lower()
        assert d.sentiment == "Negative"

    def test_food_taste_not_pool_with_sticky_context(self):
        clause = (
            "Yemeklerde cidden lezzet yok hem kuş kadar yapıyorlar kimseye yetmiyor "
            "hem de tatları kötü yani tat alma duyumu kaybettim sandım her şeyin tadı birbirine benziyor garip baya."
        )
        d = classify_clause(clause, frame_context={"pool": True, "aquapark": True})
        assert d.aspect_key == "food_taste"
        assert "havuz" not in (d.aspect_label or "").lower()
        assert d.sentiment == "Negative"

    def test_dirty_fb_service_not_pool(self):
        clause = "Yemekte servis bekliyoruz kirli servis getiriyorlar ve gelmesi de yine 10 15 dk sürüyor."
        d = classify_clause(clause, frame_context={"pool": True})
        assert d.aspect_key in ("table_cleanliness", "housekeeping_service", "service_queue", "food_taste")
        assert "havuz" not in (d.aspect_label or "").lower()
        assert d.sentiment == "Negative"

    def test_paramiza_oldu_negative(self):
        clause = "Olan paramıza ve zamanımıza oldu."
        sent, score = detect_strong_sentiment(clause)
        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.sentiment == "Negative"

    def test_azarlars_gibi_staff_negative(self):
        clause = "Bir de azarlar gibi konuşup insanı geriyorlar."
        d = classify_clause(clause)
        assert d.sentiment == "Negative"

    def test_operations_management_weak_org(self):
        clause = (
            "Otel kapasitesine ulaşmadıklarını söylemelerine rağmen 15 metre yemek kuyrukları "
            "a la carte için 1 buçuk saat yemek beklemek havuzda şezlong bulamamak ve bu kalabalığa "
            "rağmen barda 1 2 çalışanın olması bizim her bara gittiğimizde 1 saat beklememiz "
            "oteldeki operasyon ekibinin ve organizasyonun ne kadar zayıf olduğunu gösteriyor."
        )
        d = classify_clause(clause)
        assert d.aspect_key in ("operations_management", "capacity", "service_queue", "fb_staffing", "pool_lounger")
        assert d.sentiment == "Negative"


class TestFullAbsaRegression:
    def test_no_pool_spa_default_on_non_pool_clauses(self):
        result = AbsaService.analyze(OPS_OVERLOAD_REVIEW, rating=1, multidomain=True)
        assert result.aspects

        for label in ("sap adam", "asans", "biriken", "lezzet yok", "churros", "koridorlarda"):
            matches = _find(result.aspects, label)
            assert matches, f"missing clause match for {label}"
            for a in matches:
                al = (a.aspect_label or a.aspect or "").lower()
                dept = (a.department_label or a.department or "").lower()
                assert "havuz / aktivite" not in al or "havuzda" in a.clause.lower() or "şezlong" in a.clause.lower()
                if "sap adam" in a.clause.lower():
                    assert a.aspect_key == "safety"
                    assert a.sentiment == "Negative"
                if "asansör" in a.clause.lower():
                    assert a.aspect_key == "elevator_cleanliness"
                    assert "havuz" not in al
                if "churros" in a.clause.lower():
                    assert a.aspect_key == "food_availability"
                if "lezzet" in a.clause.lower() and "asansör" not in a.clause.lower():
                    assert a.aspect_key == "food_taste"
                    assert "havuz" not in al

    def test_key_clauses_all_negative_sentiment(self):
        result = AbsaService.analyze(OPS_OVERLOAD_REVIEW, rating=1, multidomain=True)
        must_neg = _find(
            result.aspects,
            "aldanmayın", "aldanmayin", "ingilizce", "sap adam", "komik kaçıyor",
            "churros", "azarlar", "paramıza", "paramiza", "bıkmış", "bikmis",
        )
        assert must_neg
        assert all(a.sentiment == "Negative" for a in must_neg)

    def test_primary_category_not_spa_chlorine(self):
        r = classify_by_rules(OPS_OVERLOAD_REVIEW)
        assert r.category in (CAT_FOOD, CAT_STAFF, CAT_SPA) or r.category != CAT_SPA
        assert r.category != CAT_SPA or r.is_mixed

    def test_suggestion_not_spa_chlorine_for_ops_review(self):
        r = classify_by_rules(OPS_OVERLOAD_REVIEW)
        sug = build_suggestion(
            SuggestionContext(
                text=OPS_OVERLOAD_REVIEW,
                category=r.category,
                sentiment="Negative",
                keywords=["sıra", "bar", "yemek", "operasyon"],
                is_mixed=True,
            )
        )
        low = sug.lower()
        assert "klor" not in low and "ph değer" not in low
        assert any(w in low for w in ("kuyruk", "f&b", "bar", "operasyon", "housekeeping", "güvenlik", "guvenlik"))
