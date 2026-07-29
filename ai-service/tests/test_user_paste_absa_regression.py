"""Regression: user-reported ABSA failure modes (ascii + Turkish).

Covers: hamam böceği≠spa, staff shortage≠food, sindirim≠taste,
beach≠pool, overall disappointment, allergen inquiry≠food quality.
"""
from __future__ import annotations

import pytest

from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import OntologyService, reload_ontology
from app.services.suggestion_engine import SuggestionContext, build_suggestion


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()


CASES = [
    # 1. Cockroach — never spa
    (
        "Ayrica bir kezde olsa hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi",
        "pest_hygiene",
        "Negative",
        ("spa", "masaj", "yemek lezzeti", "yemek kalitesi"),
    ),
    (
        "Ayrıca bir kez de olsa hamam böceğinin yemek salonunda önümden geçmesi hiç de iç açıcı bir durum değildi",
        "pest_hygiene",
        "Negative",
        ("spa", "masaj"),
    ),
    # 2. Staff shortage — not food quality
    (
        "Bayram donemi olmasi nedeni ile personel sayisinda yetersizlikler mevcuttu",
        "staff_shortage",
        "Negative",
        ("yemek", "lezzet", "restoran kalite"),
    ),
    (
        "Bayram dönemi olması nedeniyle personel sayısında yetersizlikler mevcuttu",
        "staff_shortage",
        "Negative",
        ("yemek lezzeti",),
    ),
    # 3. Food illness — not taste
    (
        "yemeklerden kaynakli ailecek sindirim sitemlerimizde rahatsiz eici bir durum vardi",
        "food_illness",
        "Negative",
        ("yemek lezzeti", "lezzet"),
    ),
    (
        "yemeklerden kaynaklı ailecek sindirim sistemlerimizde rahatsız edici bir durum vardı",
        "food_illness",
        "Negative",
        ("yemek lezzeti",),
    ),
    # 4. Beach / sea — not pool/spa
    (
        "ayrica denizi normal dalga disinda, su sporlarinin sahile cok yakin olmasi nedeni ile dalgali ve bulanik bir ortamda",
        "beach",
        None,  # sentiment may be Neutral/Negative
        ("spa", "havuz / aktivite kuyruğu"),
    ),
    (
        "ayrıca denizi normal dalga dışında, su sporlarının sahile çok yakın olması nedeniyle dalgalı ve bulanık bir ortamda",
        "beach",
        None,
        ("spa",),
    ),
    # 5. Overall disappointment
    (
        "Ne yazik ki beklenti altinda kalan bir tatil oldu",
        "overall_experience",
        "Negative",
        ("havuz", "aktivite kuyruğu", "spa"),
    ),
    (
        "Ne yazık ki beklenti altında kalan bir tatil oldu",
        "overall_experience",
        "Negative",
        ("havuz / aktivite kuyruğu",),
    ),
    # 6. Allergen inquiry — not food taste quality
    (
        "herhangi bir yemege karsi alerjiniz var mi",
        "allergen_protocol",
        None,
        ("yemek lezzeti", "yemek kalitesi"),
    ),
    (
        "herhangi bir yemeğe karşı alerjiniz var mı",
        "allergen_protocol",
        None,
        ("yemek lezzeti",),
    ),
]


@pytest.mark.parametrize("clause,aspect_key,sentiment,forbidden", CASES)
def test_user_paste_clause_frames(clause, aspect_key, sentiment, forbidden):
    d = classify_clause(clause)
    assert d.aspect_key == aspect_key, f"got {d.aspect_key}/{d.aspect_label} for {clause[:60]!r}"
    if sentiment:
        assert d.sentiment == sentiment, f"got {d.sentiment} for {clause[:60]!r}"
    label_l = (d.aspect_label or "").lower()
    for bad in forbidden:
        assert bad not in label_l, f"forbidden {bad!r} in {d.aspect_label!r}"


def test_cockroach_never_spa_suggestion():
    clause = "hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi"
    sug = build_suggestion(
        SuggestionContext(category="Yiyecek & İçecek (F&B)", text=clause, sentiment="Negative")
    ).lower()
    assert any(w in sug for w in ("haşere", "hasere", "pest", "hijyen", "gıda", "gida"))
    assert "spa müdürü" not in sug and "spa muduru" not in sug
    # Must not recommend spa therapist action as the primary fix
    assert "terapist/hizmet" not in sug
    assert not sug.strip().startswith("spa")


def test_cockroach_ontology_not_spa():
    r = OntologyService.map_aspect_to_department(
        "", "hamam boceginin yemek salonunda onumden gecmesi"
    )
    assert "spa" not in (r.get("aspectLabel") or "").lower()
    assert "spa" not in (r.get("departmentLabel") or "").lower()
    assert r.get("aspect_key") == "pest_hygiene"


def test_beach_with_sticky_pool_context():
    """Previous aquapark clause must not steal deniz/sahil."""
    d = classify_clause(
        "denizi normal dalga disinda su sporlarinin sahile cok yakin olmasi nedeni ile dalgali ve bulanik",
        frame_context={"pool": True, "aquapark": True},
    )
    assert d.aspect_key == "beach"


def test_full_review_critical_aspects():
    from unittest.mock import MagicMock
    from app.services.rag_service import RagService
    from app.services.absa_service import AbsaService

    RagService.generate_suggestion = MagicMock(return_value="mocked")
    text = (
        'Ayrica yemekler ile ilgili otele girer girmez ilk soru "herhangi bir yemege karsi alerjiniz var mi" '
        "sorusu ile baslayan deneyimde basta standart bir soru olarak gorurken ilk bir kac gun yemeklerden kaynakli "
        "ailecek sindirim sitemlerimizde rahatsiz eici bir durum vardi. Bayram donemi olmasi nedeni ile personel "
        "sayisinda yetersizlikler mevcuttu. "
        "Ayrica bir kezde olsa hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi. "
        "Havuzlari, Aqua parki anlaminda genel anlamda olumlu bir otel. "
        "ayrica denizi normal dalga disinda, su sporlarinin sahile cok yakin olmasi nedeni ile dalgali ve bulanik bir ortamda. "
        "Ne yazik ki beklenti altinda kalan bir tatil oldu."
    )
    res = AbsaService.analyze_multidomain(text)
    keys = {getattr(a, "aspect", None) or getattr(a, "aspect_key", None) for a in res.aspects}
    labels = " | ".join((a.aspect_label or a.aspect or "") for a in res.aspects).lower()
    assert "pest_hygiene" in keys or "haşere" in labels or "hasere" in labels
    assert "staff_shortage" in keys or "yetersiz" in labels
    assert "food_illness" in keys or "sindirim" in labels or "güvenlik" in labels
    assert "beach" in keys or "plaj" in labels or "deniz" in labels
    assert res.overall_sentiment in ("Negative", "Mixed")
    # No spa for cockroach
    for a in res.aspects:
        cl = (a.clause or "").lower()
        if "bocek" in cl or "böcek" in cl:
            assert "spa" not in (a.aspect_label or "").lower()
            assert "spa" not in (a.department_label or "").lower()
    summary = (getattr(res, "operational_summary", "") or "").lower()
    assert summary
    assert "26.05" not in summary
    assert any(w in summary for w in ("böcek", "bocek", "haşere", "hasere", "sindirim", "personel", "otopark", "banyo", "hijyen"))
