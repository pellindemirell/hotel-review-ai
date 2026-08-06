"""Regression: mixed Turkish resort review — queue, privacy, pool temp, alakart.

Must NOT map unrelated clauses to HVAC Soğutma / Teknik; overall Mixed;
quoted 'sorry, sorry' stays intact; operational themes in summary.
Queue department follows context frames (pool/kids ≠ F&B; alakart/bar = F&B).
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
from app.services.ontology_service import OntologyService, reload_ontology
from app.services.rag_service import RagService
from app.services.suggestion_engine import SuggestionContext, build_suggestion
from app.services.turkish_nlp_utils import CAT_FOOD, CAT_TECH, analyze_mixed_review

MIXED_RESORT_REVIEW = (
    "Otel çok büyük yürümeyi sevmeyen kesinlikle tercih etmemeli. "
    "Su kaydıraklarının oradaki havuzdan denize yürümek bile uzun sürüyor. "
    "açık iki havuz var ve ikisi de 1.40 ve her zaman çok sıcak asla serinletmiyor ve çok kalabalık havuzlar. "
    "Genel olarak çok keyifli geçen nir tatildi. Ancak otel çok kalabalık ve o kadar kişinin oturabileceği yeterli alan yok. "
    "Otel odaları çok küçük. Barlardaki çalışan sayıları çok az. "
    "Gece gündüz fark etmeden sürekli sıra beklemeniz gerekiyor. "
    "Su kaydırakları çok güzel ama oteldeki çocuk sayısı aşırı fazla olduğu için belki yarım saat sıra beklemeniz gerekiyor. "
    "Çalışanlar oldukça ilgili ve güler yüzlü insanlar ancak benim başıma gelip hoşuma gitmeyen bir durum oldu ki "
    "kapıda temizlikle alakalı bir şey asılı değildi ancak bir anda temizlik çalışanı odaya girdi ve saçını kuruturken "
    "bir anda onu görünce ne olduğunu anlayamadım. Bir anda odadan \"sorry, sorry\" diyerek çıksa da hoş değildi. "
    "Sonrasında kapının önünde \"cleaning cleaning\" diyip durdu anca odada zaten ben varken temizlik olması biraz saçma olurdu. "
    "Gene de çalıştırdığın makinenin sesinin dışarıdan duyulmamasına imkan yok. Zaten kapının önünde kurutuyordum saçımı. "
    "Ama bunun yanında oldukça iyiydi. "
    "Özellikle de mojitadaki sanıyorum ki adı Umut olan genç çocuğun güler yüzlülüğü tatilde beni keyiflendiren durumlardan bir tanesi oldu. "
    "Yemekler güzel ancak sabahları sıkma portakal suyunun paralı olması gereksizdi. "
    "Bu otel zincirinin farklı bir oteline de daha önce gitmiştim ve böyle değildi. "
    "Alakart hakkının bir olmaması ve istediğiniz alakarta istediğiniz kadar gidebilmeniz oldukça keyifli olsa da "
    "alakartta bir yer bulmak için oldukça sıra beklemeniz gerekiyor çünkü alakartların hepsi çok yavaş işliyor. "
    "Ve yer tutma muhabbetti havuz ve denizde de geçerli genelde erken gitmezseniz yer bulamazsınız. "
    "Ama genel olarak oldukça keyif aldığım ve mutlu bir şekilde ayrıldığım otel oldu. "
    "Olumsuzluklar üzerinden gidip yorum yapmış olsam da genel bazdan baktığımda gayet güzel geçen bir tatildi. "
    "Akşamlaro olan etkinliklerden her bir akşam fazlasıyla keyif aldık. "
    "Bütün etkinlikleri aşırı keyifli bir eğlenceyle izledik animasyon ekibi oldukça başarılıydı."
)


def _find_clause(aspects, needle: str):
    needle = needle.lower()
    for a in aspects:
        if needle in a.clause.lower():
            return a
    return None


def _is_fb(label: str) -> bool:
    low = (label or "").lower()
    return "f&b" in low or "yiyecek" in low or "restoran" in low or low == "bar"


def _is_leisure(label: str) -> bool:
    low = (label or "").lower()
    return "rekreasyon" in low or "eğlence" in low or "eglence" in low or "havuz" in low


@pytest.fixture(autouse=True)
def _reload():
    reload_ontology()
    reload_pipeline_config()
    yield


class TestSegmentation:
    def test_sorry_quote_not_split(self):
        parts = split_clauses_absa(
            'Bir anda odadan "sorry, sorry" diyerek çıksa da hoş değildi.'
        )
        assert len(parts) == 1
        assert "sorry, sorry" in parts[0]

    def test_sorry_curly_quote_not_split(self):
        parts = split_clauses_absa(
            "Bir anda odadan \u201csorry, sorry\u201d diyerek çıksa da hoş değildi."
        )
        assert len(parts) == 1
        assert "sorry" in parts[0].lower()

    def test_yer_tutma_havuz_deniz_single_clause(self):
        parts = split_clauses_absa(
            "Ve yer tutma muhabbetti havuz ve denizde de geçerli genelde erken gitmezseniz yer bulamazsınız."
        )
        assert len(parts) == 1
        assert "havuz" in parts[0] and "deniz" in parts[0]


class TestClausePipelineCorrections:
    def test_bar_queue_not_hvac(self):
        clause = "Gece gündüz fark etmeden sürekli sıra beklemeniz gerekiyor"
        d = classify_clause(clause)
        assert d.aspect_key == "service_queue"
        assert "teknik" not in d.department_label.lower()
        assert d.sentiment == "Negative"

        m = OntologyService.map_aspect_to_department(clause, clause)
        assert m.get("aspect_key") in ("service_queue", "food_queue", "pool_queue", "queue_waiting")
        assert "soğutma" not in (m.get("aspectLabel") or "").lower()
        assert "teknik" not in (m.get("departmentLabel") or "").lower()

        r = AbsaService.analyze(clause, multidomain=True)
        assert r.aspects, "expected at least one aspect"
        a = r.aspects[0]
        assert a.aspect_key in ("service_queue", "queue_waiting")
        assert _is_fb(a.department_label or "")

    def test_alakart_queue_fb(self):
        d = classify_clause(
            "alakartta bir yer bulmak için oldukça sıra beklemeniz gerekiyor çünkü alakartların hepsi çok yavaş işliyor"
        )
        assert d.aspect_key == "service_queue"
        assert _is_fb(d.department_label)

    def test_kids_aquapark_queue_not_fb(self):
        d = classify_clause(
            "oteldeki çocuk sayısı aşırı fazla olduğu için belki yarım saat sıra beklemeniz gerekiyor"
        )
        assert d.aspect_key in ("pool_queue", "capacity", "kids_capacity")
        assert not _is_fb(d.department_label)
        assert _is_leisure(d.department_label) or "atmosfer" in d.department_label.lower()
        assert d.sentiment == "Negative"

        contrast = classify_clause(
            "Su kaydırakları çok güzel ama oteldeki çocuk sayısı aşırı fazla olduğu için belki yarım saat sıra beklemeniz gerekiyor.",
            frame_context={"last_queue_venue": "pool", "pool": True, "aquapark": True},
        )
        if "sıra" in contrast.clause.lower() or "sira" in contrast.clause.lower():
            assert not _is_fb(contrast.department_label)

    def test_walk_distance_not_fb_queue(self):
        d = classify_clause(
            "Su kaydıraklarının oradaki havuzdan denize yürümek bile uzun sürüyor."
        )
        assert d.aspect_key in ("property_walkability", "location", "guest_experience", "pool_lounger")
        assert d.aspect_key != "service_queue"
        assert not _is_fb(d.department_label)

    def test_common_area_capacity_not_hk(self):
        d = classify_clause(
            "otel çok kalabalık ve o kadar kişinin oturabileceği yeterli alan yok"
        )
        assert d.aspect_key in ("capacity", "kids_capacity", "guest_experience")
        assert "temizlik" not in d.aspect_label.lower()

    def test_bar_staff_count_fb(self):
        d = classify_clause("Barlardaki çalışan sayıları çok az.")
        assert d.aspect_key == "fb_staffing"
        assert _is_fb(d.department_label)
        assert d.sentiment == "Negative"

    def test_property_size_not_room_size(self):
        d = classify_clause("Otel çok büyük yürümeyi sevmeyen kesinlikle tercih etmemeli.")
        assert d.aspect_key in ("property_walkability", "location", "guest_experience")
        assert d.aspect_key != "room_size"

    def test_pool_hot_not_hvac(self):
        d = classify_clause(
            "açık iki havuz var ve ikisi de 1.40 ve her zaman çok sıcak asla serinletmiyor ve çok kalabalık havuzlar"
        )
        assert d.aspect_key in ("pool_lounger", "pool_queue", "capacity")
        assert "soğutma" not in d.aspect_label.lower()
        assert d.sentiment == "Negative"

    def test_housekeeping_privacy_negative(self):
        d = classify_clause(
            'benim başıma gelip hoşuma gitmeyen bir durum oldu ki kapıda temizlikle alakalı bir şey asılı değildi'
        )
        assert d.aspect_key == "housekeeping_privacy"
        assert d.sentiment == "Negative"

    def test_sunbed_capacity(self):
        d = classify_clause(
            "Ve yer tutma muhabbetti havuz ve denizde de geçerli genelde erken gitmezseniz yer bulamazsınız"
        )
        assert d.aspect_key in ("pool_lounger", "capacity", "pool_queue")
        assert "teknik" not in d.department_label.lower()

    def test_portakal_extra_charge(self):
        clause = "sabahları sıkma portakal suyunun paralı olması gereksizdi"
        d = classify_clause(clause)
        assert d.aspect_key == "fb_extra_charge"
        assert d.aspect_key != "food_taste"
        assert "lezzet" not in (d.aspect_label or "").lower()
        assert _is_fb(d.department_label or "")
        assert d.sentiment == "Negative"
        sug = build_suggestion(
            SuggestionContext(
                category=d.department_label or "Yiyecek & İçecek (F&B)",
                text=clause,
                sentiment="Negative",
            )
        )
        low = sug.lower()
        assert any(w in low for w in ("ücret", "ucret", "paralı", "fiyat", "dahil", "politika"))
        assert "lezzet" not in low
        assert "tadım" not in low

    def test_animation_no_eq_iron(self):
        clause = "Bütün etkinlikleri aşırı keyifli bir eğlenceyle izledik animasyon ekibi oldukça başarılıydı."
        d = classify_clause(clause)
        assert d.aspect_key == "animation"
        ents = OntologyService.search_entity(clause)
        assert not any((e.get("entity_key") or e.get("entity_id")) == "eq_iron" for e in ents)

    def test_aksamlaro_keyif_aldik_positive_praise(self):
        """Typoed evening-activity praise must be Positive — never cancel/masa tenisi suggestion."""
        clause = "Akşamlaro olan etkinliklerden her bir akşam fazlasıyla keyif aldık."
        from app.services.turkish_nlp_utils import detect_strong_sentiment, normalize_turkish

        norm = normalize_turkish(clause)
        assert "akşamlara" in norm or "aksamlara" in norm.replace("ş", "s")
        assert "keyif" in norm

        sent, score = detect_strong_sentiment(clause)
        assert sent == "Positive", f"expected Positive from lexicon, got {sent} ({score})"
        assert score > 0.08

        d = classify_clause(clause, base_sentiment=sent, base_score=score)
        assert d.aspect_key == "animation"
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0
        dept = (d.department_label or "").lower()
        assert any(w in dept for w in ("animasyon", "etkinlik", "rekreasyon", "eğlence", "eglence"))

        sug = build_suggestion(
            SuggestionContext(
                category=d.department_label or "Rekreasyon & Eğlence",
                text=clause,
                sentiment=d.sentiment,
            )
        )
        low = sug.lower()
        assert "iptal" not in low
        assert "masa tenisi" not in low
        assert "bayram" not in low
        assert any(w in low for w in ("olumlu", "takdir", "paylaşılmalı", "korun", "teşekkür", "tesekkur"))

        r = AbsaService.analyze(clause, multidomain=True)
        assert r.aspects
        a = r.aspects[0]
        assert a.sentiment == "Positive"
        assert a.aspect_key == "animation"
        asug = (a.suggestion or "").lower()
        assert "iptal" not in asug
        assert "masa tenisi" not in asug


class TestFullReviewAbsa:
    def test_primary_not_teknik(self):
        r = classify_by_rules(MIXED_RESORT_REVIEW)
        assert r.category != CAT_TECH
        assert r.category == CAT_FOOD

    def test_overall_mixed(self):
        result = AbsaService.analyze(MIXED_RESORT_REVIEW, multidomain=True)
        assert result.overall_sentiment == "Mixed"
        mixed = analyze_mixed_review(MIXED_RESORT_REVIEW)
        assert mixed.is_mixed is True

    def test_no_hvac_cooling_bleed(self):
        result = AbsaService.analyze(MIXED_RESORT_REVIEW, multidomain=True)
        hvac = [
            a for a in result.aspects
            if "soğutma" in (a.aspect_label or "").lower()
            or a.aspect_key in ("hvac_cooling", "hvac_not_cooling", "tech_general")
        ]
        assert not hvac, f"HVAC bleed: {[a.clause[:50] for a in hvac]}"

    def test_key_clause_mappings(self):
        result = AbsaService.analyze(MIXED_RESORT_REVIEW, multidomain=True)

        bare_queue = _find_clause(result.aspects, "gece gündüz fark etmeden")
        assert bare_queue is not None
        assert bare_queue.aspect_key == "service_queue"
        assert bare_queue.sentiment == "Negative"
        assert _is_fb(bare_queue.department_label or "")

        kids_queue = _find_clause(result.aspects, "çocuk sayısı aşırı fazla")
        assert kids_queue is not None
        assert kids_queue.aspect_key in ("pool_queue", "capacity", "kids_capacity")
        assert not _is_fb(kids_queue.department_label or "")
        assert kids_queue.sentiment == "Negative"

        walk = _find_clause(result.aspects, "havuzdan denize yürümek")
        assert walk is not None
        assert walk.aspect_key != "service_queue"
        assert not _is_fb(walk.department_label or "")

        area = _find_clause(result.aspects, "oturabileceği yeterli alan")
        assert area is not None
        assert area.aspect_key in ("capacity", "kids_capacity", "guest_experience")
        assert "temizlik" not in (area.aspect_label or "").lower()

        bar_staff = _find_clause(result.aspects, "barlardaki çalışan")
        assert bar_staff is not None
        assert bar_staff.aspect_key == "fb_staffing"
        assert _is_fb(bar_staff.department_label or "")

        prop = _find_clause(result.aspects, "yürümeyi sevmeyen")
        assert prop is not None
        assert prop.aspect_key != "room_size"

        privacy = _find_clause(result.aspects, "hoşuma gitmeyen")
        assert privacy is not None
        assert privacy.aspect_key == "housekeeping_privacy"
        assert privacy.sentiment == "Negative"
        assert "olumlu temizlik" not in (privacy.suggestion or "").lower()

        sorry = _find_clause(result.aspects, "sorry")
        assert sorry is not None
        assert "sorry" in sorry.clause.lower()

        alakart = _find_clause(result.aspects, "alakartta bir yer")
        assert alakart is not None
        assert alakart.aspect_key == "service_queue"
        assert _is_fb(alakart.department_label or "")

        sunbed = _find_clause(result.aspects, "yer tutma muhabbetti")
        assert sunbed is not None
        assert sunbed.aspect_key in ("pool_lounger", "capacity", "pool")
        assert "teknik" not in (sunbed.department_label or "").lower()

        anim = _find_clause(result.aspects, "animasyon ekibi")
        assert anim is not None
        assert anim.aspect_key == "animation"
        assert anim.sentiment == "Positive"
        assert getattr(anim, "entity_id", None) != "eq_iron"
        assert anim.aspect_key != "eq_iron"

        keyif_eve = _find_clause(result.aspects, "fazlasıyla keyif") or _find_clause(
            result.aspects, "keyif aldık"
        )
        assert keyif_eve is not None
        assert keyif_eve.sentiment == "Positive"
        assert keyif_eve.aspect_key == "animation"
        ke_sug = (keyif_eve.suggestion or "").lower()
        assert "iptal" not in ke_sug
        assert "masa tenisi" not in ke_sug

        portakal = _find_clause(result.aspects, "portakal suyunun paralı")
        assert portakal is not None
        assert portakal.sentiment == "Negative"
        assert portakal.aspect_key == "fb_extra_charge"
        assert portakal.aspect_key != "food_taste"
        assert _is_fb(portakal.department_label or "")
        sug = (portakal.suggestion or "").lower()
        assert sug
        assert "lezzet" not in sug and "tadım" not in sug
        assert any(w in sug for w in ("ücret", "ucret", "dahil", "politika", "fiyat", "ücretli"))

    def test_summary_multi_theme(self):
        summary = RagService.generate_summary(MIXED_RESORT_REVIEW)
        low = summary.lower()
        assert len(summary.split()) >= 8
        assert any(w in low for w in ("sıra", "sira", "kuyruk", "bekle", "bar", "içecek", "icecek", "havuz", "kapasite"))
        assert "soğutma" not in low
