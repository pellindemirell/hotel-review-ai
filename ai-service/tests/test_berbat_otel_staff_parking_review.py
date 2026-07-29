"""Regression: 'en berbat otel' — staff immaturity, parking, no-recommend routing."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.absa_service import AbsaService
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import OntologyService, reload_ontology

BERBAT_OTEL_REVIEW = (
    "Hayatım boyunca gittiğim en berbat oteldi gerçekten . kurban bayramı tatilimi bukadar kötü geçiremezdim . "
    "Personeller coluk çocuk yabancı çoğu  otel sanki çocukların eline bırakılmış gidilmiş gibi . "
    "Paramızla rezil olduk . Yemin ederim tam anlamıyla şunu söyleyebilirim ki toplama kampından farkı yok . "
    "Personeller müşterilere kaba davranıyor ve sürekli tartışma çıkıyordu. "
    "Arabamı bile otoparka koyamadım yer yok diye bu kadar müşteriyi agırlamasını biliyorsanız para için  ona göre otoparkınız olacak . "
    "Hergün dışarı çıkıp arabayı kontrol ettim . Rezil olmak isteyen varsa parasıyla buyursun gitsin . "
    "Ben kimseye tavsiye etmem çevremden kimseyide bu otele göndermem"
)


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()
    yield


def _find(aspects, *needles: str):
    return [a for a in aspects if any(n.lower() in a.clause.lower() for n in needles)]


class TestBerbatClauseLevel:
    def test_staff_children_not_bar_or_aquapark(self):
        clause = (
            "Personeller coluk çocuk yabancı çoğu otel sanki çocukların eline bırakılmış gidilmiş gibi"
        )
        d = classify_clause(clause)
        assert d.aspect_key == "staff_behavior"
        assert d.sentiment == "Negative"
        low = (d.department_label or "").lower()
        assert "bar" not in low
        assert "içecek" not in low and "icecek" not in low
        assert "personel" in low

        ont = OntologyService.map_aspect_to_department(clause, clause) or {}
        assert ont.get("aspect_key") != "drink_quality"
        assert "bar" not in (ont.get("departmentLabel") or "").lower()

    def test_tavsiye_etmem_general_not_hk(self):
        clause = "Ben kimseye tavsiye etmem çevremden kimseyide bu otele göndermem"
        d = classify_clause(clause)
        assert d.sentiment == "Negative"
        assert d.aspect_key == "guest_experience"
        assert "temizlik" not in (d.department_label or "").lower()
        assert "housekeeping" not in (d.department_label or "").lower()

    def test_parking_car_check_negative(self):
        clause = "Hergün dışarı çıkıp arabayı kontrol ettim"
        d = classify_clause(
            clause,
            frame_context={"parking": True, "last_parking": True},
        )
        assert d.sentiment == "Negative"
        assert d.aspect_key in ("parking", "guest_experience", "general")

    def test_worst_hotel_critical_negative(self):
        d = classify_clause("Hayatım boyunca gittiğim en berbat oteldi gerçekten")
        assert d.sentiment == "Negative"
        assert d.sentiment_score <= -0.65
        assert d.aspect_key in ("guest_experience", "overall_experience", "general")


class TestBerbatFullReview:
    def test_overall_strongly_negative(self):
        result = AbsaService.analyze(BERBAT_OTEL_REVIEW, rating=1, multidomain=True)
        assert result.overall_sentiment == "Negative"
        assert (result.overall_score or 0) <= -0.5

    def test_key_clauses_routing(self):
        result = AbsaService.analyze(BERBAT_OTEL_REVIEW, rating=1, multidomain=True)

        staff_kids = _find(result.aspects, "coluk", "çocukların eline", "cocuklarin eline")
        assert staff_kids
        for a in staff_kids:
            assert a.aspect_key == "staff_behavior"
            assert a.sentiment == "Negative"
            dept = (a.department_label or "").lower()
            assert "bar" not in dept
            assert "personel" in dept
            sug = (a.suggestion or "").lower()
            assert "aquapark" not in sug and "klor" not in sug

        tavsiye = _find(result.aspects, "tavsiye etmem")
        assert tavsiye
        for a in tavsiye:
            assert a.sentiment == "Negative"
            assert "temizlik" not in (a.department_label or "").lower()
            assert a.aspect_key in ("guest_experience", "overall_experience", "general")

        parking = _find(result.aspects, "otopark", "arabam")
        assert parking
        for a in parking:
            assert a.sentiment == "Negative"
            assert a.aspect_key == "parking" or "otopark" in (a.department_label or "").lower()

        worst = _find(result.aspects, "en berbat")
        assert worst
        assert all(a.sentiment == "Negative" for a in worst)
        assert any(a.priority in ("critical", "high") or a.priority_score >= 3 for a in worst)
