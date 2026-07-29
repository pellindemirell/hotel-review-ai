"""Overnight edge-case regression: konser/kids/havuz+masaj/disclaimer."""
from __future__ import annotations

from app.services.absa_service import AbsaService
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import reload_ontology


def setup_module():
    reload_pipeline_config()
    reload_ontology()


def _labels(text: str):
    r = AbsaService.analyze_multidomain(text)
    assert r.aspects, f"no aspects for: {text}"
    return r, [(a.department_label, a.sentiment, getattr(a, "aspect_key", None), a.clause) for a in r.aspects]


def test_konserler_ve_begendim_stays_animation_positive():
    text = "konserler vardi ve cok begendim"
    r, rows = _labels(text)
    depts = {d for d, *_ in rows}
    assert any("Animasyon" in d or "Rekreasyon" in d for d in depts)
    assert all(s in ("Positive", "Neutral") for _, s, *_ in rows)
    assert r.overall_sentiment in ("Positive", "Mixed", "Neutral")
    # Short praise must stay attached (no orphan "begendim" staff clause)
    assert len(r.aspects) <= 2


def test_kids_club_personel_az_is_kids_club_not_generic_staff():
    text = "kids club saatleri kısıtlı ve personel azdı"
    r, rows = _labels(text)
    assert any(
        (getattr(a, "aspect_key", None) == "kids_club")
        or ("Animasyon" in (a.department_label or ""))
        or ("Çocuk" in (a.aspect_label or ""))
        for a in r.aspects
    )
    # Should not collapse solely to generic Personel Davranışı
    primary = r.aspects[0]
    assert "Personel" not in (primary.department_label or "") or getattr(primary, "aspect_key", None) == "kids_club"
    assert any(s == "Negative" for _, s, *_ in rows)


def test_havuz_temiz_masaj_priority_is_havuz():
    text = "havuz temiz masaj harikaydı"
    r, rows = _labels(text)
    assert any(
        d in ("Havuz", "Rekreasyon & Eğlence", "Plaj & Deniz") or "Havuz" in d
        for d, *_ in rows
    )
    # Must not become Spa-only when both havuz + masaj present
    assert not all((d == "Spa" or "Spa" in d) for d, *_ in rows)
    assert any(s == "Positive" for _, s, *_ in rows)


def test_aquapark_bakima_ihtiyaci_is_havuz_not_teknik():
    text = "3 aquaprk var 1'i kapalıydı bir tanesinin ciddi bakıma ihtiyacı var"
    r, rows = _labels(text)
    for a in r.aspects:
        cl = (a.clause or "").lower()
        if "bakim" in cl or "bakım" in cl or "aquaprk" in cl or "aquapark" in cl:
            assert a.department_label in ("Havuz", "Rekreasyon & Eğlence")
            assert "Teknik" not in (a.department_label or "")


def test_disclaimer_positive_review_not_forced_negative():
    text = (
        "olumsuz yorum yapanlara aldırış yapmayın bir cogu doğuştan memnuniyetsiz, "
        "otel 2015 yapımı genç yapı, odalar genis en düşük 25 m2, genis havuzlar ve suparkı mevcut "
        "3000 kişi kapasiteli elbette kalabalık olacak, sabah kahvaltısı 07.00 11.00 kadar bunu hiç bir otelde bulamazsınız, "
        "akşam yemeği 18.30 21.30 yeme içme sınırsız sabaha kadar daha ne olsun, mutfak çeşiti çok zengin yazılanlara inanmayın, "
        "çocuklu ailelere uygun, sadece kötü yanı otel çok büyük, iyi tatiller dilerim"
    )
    r = AbsaService.analyze_multidomain(text)
    assert r.aspects
    assert r.overall_sentiment in ("Positive", "Mixed", "Neutral")
    # Disclaimer opener must not force Negative overall alone
    opener = next((a for a in r.aspects if "olumsuz yorum" in (a.clause or "").lower()), None)
    if opener:
        assert opener.sentiment in ("Positive", "Neutral", "Mixed") or r.overall_sentiment != "Negative"


def test_hicbir_sorun_yasamadik_positive_guard():
    d = classify_clause("Personel her zaman güler yüzlüydü hiçbir sorun yaşamadık")
    assert d.sentiment == "Positive"
    assert d.sentiment_score > 0
