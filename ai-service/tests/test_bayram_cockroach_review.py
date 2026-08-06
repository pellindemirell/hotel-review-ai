"""Regression: Bayram / cockroach / food illness / beach review (user-reported failures)."""
from __future__ import annotations

import pytest

from app.ontology.engine import reload_hotel_ontology_engine
from app.services.absa_service import AbsaService
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import OntologyService, reload_ontology


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()
    reload_hotel_ontology_engine()


BAYRAM_REVIEW = (
    '" sorusu ile baslayan deneyimde basta standart bir soru olarak gorurken ilk bir kac gun '
    "yemeklerden kaynakli ailecek sindirim sitemlerimizde rahatsiz eici bir durum vardi. "
    "Bayram donemi olmasi nedeni ile personel sayisinda yetersizlikler mevcuttu. "
    "26.05-30.05 2026 da 4 gece Bes Gun kaldigim bu otel hakkinda goruslerim, "
    "Oncelikle Otopark ve araci otelden uzakta toprak bir zemin uzerinde tozun icerisinde birakmak "
    "ile baslayan bu deneyim, Odalarin ozellikle banyo ksimlarinin yenilenmesi gerekliligi ile de "
    "bekledigimin altinda bir oda kalitesine sahipti. "
    "Ayrica bir kezde olsa hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi. "
    "Aqua parkalrda sadece havuz derinlikleri cocukalra gore ayarlanmis, boy-kilo gibi "
    "(ozellikle uzun ve agir kisilerin ) kaza gecirebilmekte. "
    "Havuzlari, Aqua parki anlaminda genel anlamda olumlu bir otel. "
    "ayrica denizi normal dalga disinda, su sporlarinin sahile cok yakin olmasi nedeni ile "
    "dalgali ve bulanik bir ortamda. "
    "Ne yazik ki beklenti altinda kalan bir tatil oldu."
)


class TestClausePipelineCriticalFrames:
    def test_hamam_bocegi_not_spa(self):
        clause = "hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi"
        d = classify_clause(clause)
        assert d.aspect_key == "pest_hygiene"
        assert "spa" not in (d.department_label or "").lower()
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_personel_yetersizlik_not_food(self):
        clause = "Bayram donemi olmasi nedeni ile personel sayisinda yetersizlikler mevcuttu"
        d = classify_clause(clause)
        assert d.aspect_key == "staff_shortage"
        assert d.aspect_key != "food_taste"
        assert "personel" in (d.department_label or "").lower()
        assert d.sentiment == "Negative"

    def test_sindirim_not_taste(self):
        clause = "yemeklerden kaynakli ailecek sindirim sitemlerimizde rahatsiz eici bir durum vardi"
        d = classify_clause(clause)
        assert d.aspect_key == "food_illness"
        assert d.aspect_key != "food_taste"
        assert "lezzet" not in (d.aspect_label or "").lower()
        assert d.sentiment == "Negative"

    def test_deniz_su_sporlari_not_pool(self):
        clause = (
            "ayrica denizi normal dalga disinda, su sporlarinin sahile cok yakin olmasi "
            "nedeni ile dalgali ve bulanik bir ortamda"
        )
        d = classify_clause(clause)
        assert d.aspect_key == "beach"
        assert d.aspect_key not in ("pool_lounger", "pool_queue", "spa")
        assert d.sentiment == "Negative"

    def test_beklenti_altinda_not_queue(self):
        clause = "Ne yazik ki beklenti altinda kalan bir tatil oldu"
        d = classify_clause(clause)
        assert d.aspect_key == "overall_experience"
        assert d.aspect_key not in ("pool_queue", "service_queue", "pool_lounger")
        assert d.sentiment == "Negative"

    def test_alerji_not_food_taste_positive(self):
        clause = "herhangi bir yemege karsi alerjiniz var mi sorusu ile baslayan deneyimde"
        d = classify_clause(clause)
        assert d.aspect_key == "allergen_protocol"
        assert d.aspect_key != "food_taste"
        assert d.sentiment != "Positive" or d.sentiment_score <= 0.35

    def test_harika_degil_negative(self):
        d = classify_clause("harika değil, otel berbat")
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_memnun_etti_positive(self):
        d = classify_clause("bizi memnun etti")
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0


class TestFullBayramReview:
    def test_overall_not_neutral_when_critical_complaints(self):
        result = AbsaService.analyze_multidomain(BAYRAM_REVIEW)
        assert result.overall_sentiment in ("Negative", "Mixed")
        assert (result.overall_score or 0) <= 0.15

    def test_key_negative_clauses_present(self):
        result = AbsaService.analyze_multidomain(BAYRAM_REVIEW)
        rows = [
            {
                "clause": a.clause.lower(),
                "aspect_key": getattr(a, "aspect_key", None) or a.aspect or "",
                "sentiment": a.sentiment,
                "dept": (a.department_label or a.department or "").lower(),
            }
            for a in result.aspects
        ]

        def find(needle: str):
            for r in rows:
                if needle in r["clause"]:
                    return r
            return None

        cockroach = find("hamam boceg")
        assert cockroach is not None
        assert cockroach["sentiment"] == "Negative"
        assert cockroach["aspect_key"] == "pest_hygiene"
        assert "spa" not in cockroach["dept"]

        staff = find("personel sayisinda")
        assert staff is not None
        assert staff["aspect_key"] == "staff_shortage"
        assert staff["sentiment"] == "Negative"

        beach = find("dalgali ve bulanik")
        assert beach is not None
        assert beach["aspect_key"] == "beach"
        assert beach["sentiment"] == "Negative"
        assert "spa" not in beach["dept"]

        overall = find("beklenti altinda")
        assert overall is not None
        assert overall["sentiment"] == "Negative"
