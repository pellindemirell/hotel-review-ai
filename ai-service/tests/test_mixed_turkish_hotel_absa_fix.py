"""Regression: mixed Turkish hotel review — praise polarity, FO queue, F&B ops, shower false entity."""
from __future__ import annotations

import pytest

from app.ontology.engine import reload_hotel_ontology_engine
from app.services.absa_service import AbsaService
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import OntologyService, reload_ontology
from app.services.turkish_nlp_utils import analyze_sentiment_with_rating


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()
    reload_hotel_ontology_engine()
    yield


def _is_fb(label: str) -> bool:
    low = (label or "").lower()
    return "f&b" in low or "yiyecek" in low or "restoran" in low


def _is_fo(label: str) -> bool:
    low = (label or "").lower()
    return "ön büro" in low or "on buro" in low or "front" in low or "resepsiyon" in low


class TestPraisePolarity:
    def test_bizi_memnun_etti_positive(self):
        d = classify_clause("bizi memnun etti")
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0
        sent, score = analyze_sentiment_with_rating("bizi memnun etti")
        assert sent == "Positive"
        assert score > 0

    def test_memnun_ettiler_positive(self):
        d = classify_clause("personeller bizi çok memnun ettiler")
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0

    def test_keyiflendirdi_positive(self):
        d = classify_clause("le coruasante bölümündeki notlar günümüzü keyiflendirdi")
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0

    def test_hosnut_kalmamadigim_alacarte_negative(self):
        clause = "bu otelde hoşnut kalmamadığım en önemli yer alacarte restorantlardı"
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert _is_fb(d.department_label)
        assert d.aspect_key in (
            "a_la_carte_quality", "food_taste", "restaurant_hours", "food_availability"
        )


class TestFrontOfficeQueue:
    def test_rezervasyonsuz_kapida_bekleyen_negative(self):
        clause = (
            "rezervasyonsuz kabulleri ile kapıda yığınla saatlerce bekleyen misafirlerle dolu"
        )
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert _is_fo(d.department_label) or d.aspect_key == "front_office"
        sent, score = analyze_sentiment_with_rating(clause)
        assert sent == "Negative"
        assert score < 0


class TestFoodBeverageOps:
    def test_ac_kaldi_kids_fb_negative(self):
        clause = "yedi yaşındaki kızım aç kaldığı için sorun yaşadık"
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert _is_fb(d.department_label)
        assert d.aspect_key in ("food_availability", "restaurant_hours", "food_taste")

    def test_yemegin_bittigi_restaurant_hours_negative(self):
        clause = (
            "akşam saat 22:00'da gitmemize rağmen yemeğin bittiği söylenildi "
            "ve kapısından içeriye alındık"
        )
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert _is_fb(d.department_label)
        assert d.aspect_key in (
            "restaurant_hours", "food_availability", "service_queue", "food_taste"
        )


class TestShowerFalseEntity:
    def test_dusurulmus_not_handheld_shower(self):
        clause = "çok güzel düşünülmüş"
        ents = OntologyService.search_entity(clause)
        assert not any(e.get("entity_id") == "eq_handheld_shower" for e in ents)
        d = classify_clause(clause)
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0

    def test_real_el_dusu_still_resolves(self):
        ents = OntologyService.search_entity("odadaki el duşu bozuktu")
        assert any(e.get("entity_id") == "eq_handheld_shower" for e in ents)


class TestStaffPraiseIntact:
    def test_guler_yuzlu_staff_ok(self):
        d = classify_clause("personeller genel anlamda çok güler yüzlü ve ilgili.")
        assert d.sentiment == "Positive"
        assert d.aspect_key == "staff_behavior"

    def test_sedat_sef_ok(self):
        d = classify_clause("sedat şef bizimle çok ilgilendi")
        assert d.sentiment == "Positive"
        assert d.aspect_key == "staff_behavior"


class TestFullAbsaPass:
    def test_mixed_review_api_shapes(self):
        text = (
            "personeller genel anlamda çok güler yüzlü ve ilgili. "
            "bu bölümde çalışılan personeller son derece güler yüzlü bizi çok memnun ettiler. "
            "le coruasante bölümündeki kahvenin yanına verilen bu notlar günümüzü keyiflendirdi. "
            "çok güzel düşünülmüş. "
            "yedi yaşındaki kızım aç kaldığı için sorun yaşadık. "
            "bizi memnun etti. "
            "rezervasyonsuz kabulleri ile kapıda yığınla saatlerce bekleyen misafirlerle dolu. "
            "bu otelde hoşnut kalmamadığım en önemli yer alacarte restorantlardı. "
            "akşam saat 23:00'a kadar hizmet vereceğini notlarla belirtilen bu restoranlara "
            "akşam saat 22:00'da gitmemize rağmen yemeğin bittiği söylenildi. "
            "sedat şef bizimle çok ilgilendi."
        )
        result = AbsaService.analyze_multidomain(text)
        aspects = getattr(result, "aspects", None) or []
        rows = []
        for a in aspects:
            rows.append({
                "clause": getattr(a, "clause", ""),
                "sentiment": getattr(a, "sentiment", ""),
                "sentiment_score": getattr(a, "sentiment_score", 0),
                "department_label": getattr(a, "department_label", getattr(a, "department", "")),
                "aspect": getattr(a, "aspect", ""),
                "entity_id": getattr(a, "entity_id", None),
            })

        def find(needle: str):
            n = needle.lower()
            for r in rows:
                if n in (r.get("clause") or "").lower():
                    return r
            return None

        memnun = find("memnun etti")
        assert memnun is not None
        assert memnun["sentiment"] == "Positive"

        ac = find("aç kaldığı")
        assert ac is not None
        assert ac["sentiment"] == "Negative"
        assert _is_fb(ac.get("department_label") or "")

        fo = find("rezervasyonsuz")
        assert fo is not None
        assert fo["sentiment"] == "Negative"

        hosnut = find("hoşnut kalmamadığım")
        assert hosnut is not None
        assert hosnut["sentiment"] == "Negative"

        bitti = find("yemeğin bittiği")
        assert bitti is not None
        assert bitti["sentiment"] == "Negative"

        dusun = find("düşünülmüş")
        assert dusun is not None
        assert dusun["sentiment"] == "Positive"
        assert dusun.get("entity_id") not in ("eq_handheld_shower",)
