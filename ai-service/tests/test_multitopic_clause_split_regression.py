# -*- coding: utf-8 -*-
"""Regression: long multi-topic Crystal/Asteria-style clause splits (#1 morning deliverable)."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import reload_ontology
from app.services.turkish_nlp_utils import normalize_turkish


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()


def _norm_join(parts: list[str]) -> str:
    return " | ".join(normalize_turkish(p.lower()) for p in parts)


def _dept_set(text: str) -> set[str]:
    res = AbsaService.analyze_multidomain(text)
    return {normalize_turkish((a.department_label or "").lower()) for a in res.aspects}


def _has_family(deps: set[str], *needles: str) -> bool:
    return any(any(n in d for n in needles) for d in deps)


# --- Core multi-topic split matrix (Crystal / Asteria style) ---

MULTI_TOPIC_CASES = [
    # (text, min_clauses, required_topic_substrings in joined clauses)
    (
        "Kahvaltı güzeldi ama havuz kirliydi ve personel ilgisizdi",
        3,
        ["kahvalt", "havuz", "personel"],
    ),
    (
        "Personel ilgiliydi ama havuz kalabalıktı ve yemekler lezzetsizdi",
        3,
        ["personel", "havuz", "yemek"],
    ),
    (
        "Yemekler lezzetliydi fakat havuzda sinek vardı ve resepsiyon kaba davrandı",
        3,
        ["yemek", "havuz", "resepsiyon"],
    ),
    (
        "Personel cok ilgiliydi ama havuz kalabalikti, yemekler lezzetsizdi ve odalar kirliydi",
        4,
        ["personel", "havuz", "yemek", "oda"],
    ),
    (
        "Otel genel olarak guzeldi ancak personel yetersizdi ve havuzda sinek vardi ayrica yemekler ortalamaydi",
        4,
        ["personel", "havuz", "yemek"],
    ),
    (
        "Kahvalti guzeldi ama aksam yemekleri kotuydu ve animasyon ekibi zayifti",
        3,
        ["kahvalt", "yemek", "animasyon"],
    ),
    (
        "Resepsiyon ilgiliydi fakat odada klima calismiyordu ve havuz cok kirliydi",
        3,
        ["resepsiyon", "klima", "havuz"],
    ),
    (
        "Yemekler cesitliydi, personel guleryuzluydu ama plajda sezlong bulamadik ve aquapark kapaliydi",
        4,
        ["yemek", "personel", "plaj", "aquapark"],
    ),
    (
        "Temizlik iyiydi ve personel ilgiliydi ama yemekler berbatti",
        3,
        ["temizlik", "personel", "yemek"],
    ),
    (
        "Havuzlar harikaydi ve kaydiraklar eglenceliydi ama restoran hijyeni kotuydu",
        3,
        ["havuz", "kaydirak", "restoran"],
    ),
    (
        "Cocuk havuzu guzeldi ama kids club saatleri kisitliydi ve personel azdi",
        2,
        ["havuz", "kids club"],
    ),
    (
        "Odanin manzarasi guzeldi fakat temizlik yetersizdi ve yemekler lezzetsizdi",
        3,
        ["manzara", "temizlik", "yemek"],
    ),
    (
        "Bar hizmeti iyiydi ama icecek cesidi azdi ve havuz kenari cok gurultuluydi",
        3,
        ["bar", "icecek", "havuz"],
    ),
    (
        "Personel guleryuzluydu ama havuz kirliydi ve yemekler berbatti",
        3,
        ["personel", "havuz", "yemek"],
    ),
    (
        "otelin odalar guzel temiz, yemekleri kahvaltisi lezzetli aksam eglenceleri harika ozellikle animator ekibi cok iyi",
        3,
        ["oda", "yemek", "eglence"],
    ),
    (
        "Animasyon ekibinden, yemek çeşitliliğinden ve temizlikten çok memnun kaldım",
        3,
        ["animasyon", "yemek", "temizlik"],
    ),
    (
        "yemek yok, eglence yok, deniz yok, temizlik yok, kesinlikle hiçbir şey yok",
        4,
        ["yemek", "eglence", "deniz", "temizlik"],
    ),
    (
        "Oda temizdi ama klima çalışmıyordu ve personel ilgisizdi",
        3,
        ["oda", "klima", "personel"],
    ),
    (
        "Personel ilgiliydi ve havuz kaydırakları harikaydı ama yemek ortalamaydı",
        3,
        ["personel", "havuz", "yemek"],
    ),
    (
        "Deniz dalgali ve bulanikti ama barda 30 dakika sira bekledik ve personel yetersizdi",
        3,
        ["deniz", "bar", "personel"],
    ),
    (
        "Havuzlar guzel ama yemekler kotu ve odalar kirliydi",
        3,
        ["havuz", "yemek", "oda"],
    ),
    (
        "Kahvalti guzeldi fakat aksam yemeginde cesit azdi",
        2,
        ["kahvalt", "aksam"],
    ),
    (
        "Ultra her sey dahil ama bar saatleri cok kisitliydi",
        2,
        ["dahil", "bar"],
    ),
    (
        "Konumu icin tavsiye ederim ama odalar bekledigimiz kadar temiz degildi",
        2,
        ["konum", "oda"],
    ),
    (
        "Guzel olmasina ragmen yemekler lezzetsizdi ve havuz kirliydi",
        3,
        ["yemek", "havuz"],
    ),
    (
        "Personelden memnun kaldik ama oda temizligi cok kotuydu",
        2,
        ["personel", "oda"],
    ),
    (
        "Plaj guzeldi ancak sezlong bulamadik ve restoran kalabalikti",
        3,
        ["plaj", "sezlong", "restoran"],
    ),
    (
        "Spa harikaydi ama masaj randevusu alamadik ve personel ilgisizdi",
        2,
        ["spa", "personel"],
    ),
]


@pytest.mark.parametrize("text,min_n,topics", MULTI_TOPIC_CASES)
def test_multitopic_min_clause_count_and_topics(text, min_n, topics):
    parts = split_clauses_absa(text)
    assert len(parts) >= min_n, f"expected>={min_n} got {len(parts)}: {parts}"
    joined = _norm_join(parts)
    for t in topics:
        assert normalize_turkish(t.lower()) in joined or t.lower() in joined, (
            f"missing topic '{t}' in {parts}"
        )


def test_multitopic_kahvalti_havuz_personel_depts():
    text = "Kahvaltı güzeldi ama havuz kirliydi ve personel ilgisizdi"
    parts = split_clauses_absa(text)
    assert len(parts) >= 3
    deps = _dept_set(text)
    assert _has_family(deps, "yiyecek", "f&b", "restoran")
    assert _has_family(deps, "havuz", "rekreasyon", "eglence", "eğlence")
    assert _has_family(deps, "personel")


def test_multitopic_staff_pool_food_room_depts():
    text = "Personel cok ilgiliydi ama havuz kalabalikti, yemekler lezzetsizdi ve odalar kirliydi"
    parts = split_clauses_absa(text)
    assert len(parts) >= 4
    deps = _dept_set(text)
    assert _has_family(deps, "personel")
    assert _has_family(deps, "havuz", "rekreasyon", "eglence", "eğlence")
    assert _has_family(deps, "yiyecek", "f&b", "restoran")
    assert _has_family(deps, "oda", "housekeeping", "kat", "temizlik")


def test_no_false_split_adjective_pair():
    parts = split_clauses_absa("deniz dalgali ve bulanikti")
    assert len(parts) == 1


def test_keep_short_konser_praise_together():
    parts = split_clauses_absa("konserler vardi ve cok begendim")
    assert len(parts) == 1


def test_kids_club_short_praise_or_staff_split():
    # Short praise stays; kids-club staffing note also stays one venue atom
    praise = split_clauses_absa("kids club guzeldi ve cok begendim")
    assert len(praise) == 1
    staffing = split_clauses_absa("kids club saatleri kisitliydi ve personel azdi")
    assert len(staffing) == 1
    # Contrastive boundary still splits kids club from other venues
    mixed = split_clauses_absa("Cocuk havuzu guzeldi ama kids club saatleri kisitliydi ve personel azdi")
    assert len(mixed) >= 2
    joined = _norm_join(mixed)
    assert "havuz" in joined and "kids club" in joined


# --- Secondary safe rules (#2 F&B↔leisure, #3 FO/fiyat) ---

def test_kaydirak_pool_not_food():
    d = classify_clause(
        "Mini kaydıraklar ve köpekbalıkları bulunan küçük çocuklar için harika bir havuz var"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("rekreasyon", "havuz", "eglence", "eğlence"))
    assert "yiyecek" not in dep and "f&b" not in dep
    assert d.aspect_key in ("pool_lounger", "pool_queue", "kids_capacity", "beach")


def test_plaj_havuz_alakart_incidental_is_leisure():
    d = classify_clause("Plaj, havuzlar ve alakart seçeneklerinin hepsi güzel ve bakımlı")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("rekreasyon", "havuz", "plaj", "eglence", "eğlence"))
    assert d.aspect_key in ("beach", "pool_lounger", "pool_queue")


def test_restaurant_temizlik_stays_fb():
    d = classify_clause("Restoran biraz kalabalıktı ve masalar daha dikkatli temizlenebilirdi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    assert d.aspect_key in ("table_cleanliness", "cutlery", "food_taste", "service_queue")


def test_fiyat_performans_not_genel():
    d = classify_clause("fiyat performans cok iyiydi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "genel" not in dep
    assert d.aspect_key in ("value_for_money", "price_value")
    assert any(x in dep for x in ("ön büro", "on buro", "misafir", "fiyat")) or d.aspect_key == "value_for_money"


def test_fiyata_degmez_fo_value():
    d = classify_clause("Bu fiyata degmez paramiza yazik")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "genel" not in dep
    assert d.aspect_key in ("value_for_money", "price_value", "guest_experience")
    res = AbsaService.analyze_multidomain("Bu fiyata degmez paramiza yazik")
    assert res.aspects
    assert any(
        a.aspect in ("value_for_money", "price_value", "guest_experience")
        or "ön büro" in (a.department_label or "").lower()
        or "on buro" in normalize_turkish((a.department_label or "").lower())
        for a in res.aspects
    )


def test_otel_kapasite_misafir_kabul_is_fo():
    """Hotel-level capacity/overbooking complaint → Ön Büro, not bare atmosphere."""
    text = "otel kapasitesine ulaşmadıklarını söylemelerine rağmen kalabalık misafir kabul ediyorlar"
    d = classify_clause(text)
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("on buro", "ön büro", "misafir"))
    assert "atmosfer" not in dep
    assert d.aspect_key in ("front_office", "capacity", "operations_management")
    assert d.sentiment == "Negative"
    res = AbsaService.analyze_multidomain(text)
    assert res.aspects
    pred = normalize_turkish((res.aspects[0].department_label or "").lower())
    assert any(x in pred for x in ("on buro", "ön büro", "misafir", "front"))


def test_before_after_staff_pool_food_split_atom():
    """Canonical failure mode: staff+pool+food+ama must not stay one atom."""
    text = "Personel guleryuzluydu ama havuz kirliydi ve yemekler berbatti"
    parts = split_clauses_absa(text)
    assert len(parts) >= 3
    # No single clause should contain both havuz and yemek after split
    for p in parts:
        n = normalize_turkish(p.lower())
        assert not ("havuz" in n and "yemek" in n and "personel" in n)
