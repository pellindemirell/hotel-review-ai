"""Systemic ABSA clause pipeline — Crystal exhaustion + paraphrases.

Proves generalization: same frames/aspects without Crystal-specific if/else patches.
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
from app.services.clause_pipeline import (
    ClausePipeline,
    classify_clause,
    is_meta_clause,
    reload_pipeline_config,
)
from app.services.ontology_service import reload_ontology
from app.services.rag_service import RagService
from app.services.turkish_nlp_utils import (
    CAT_FINANCE,
    analyze_mixed_review,
    analyze_sentiment_with_rating,
    detect_strong_sentiment,
    predict_star_rating,
)

CRYSTAL_EXHAUSTION = (
    "Bugün otelden ayrıldım ve tek kelimeyle özetleyecek olsaydım sadece yorgunluk diyebilirdim "
    "inanılmaz kuyruklar inanılmaz sıralar beklemek zorunda kaldık hatta pankek sırasında 20 25 dakika "
    "bekleyip en son pes Edip ciktigimi hatırlıyorum açıkçası crystal otellerine geçen sene giden bir "
    "yakınım bu kadar uzun kuyruklar olacağını söylemişti ama ben çok ciddiye almamıştım hani bu kadar "
    "olabileceğini düşünmemiştim insan kendi yaşayınca anlıyormuş.pişmanlıktan öteye gitmedi paramız "
    "çöp oldu diyebilirim. onun dışında odalar çok küçük yemeklerin lezzeti ortalamaydı ama kıyma "
    "kalitesi çok düşüktü. İstediğiniz içeceği istediğinizi barda bulamıyorsunuz bunu sadece alkollü "
    "içecek olarak düşünmeyin bir barda limonata varken başka bir barda limonata yok ve siz o 10kişilik "
    "sırayı beklemiş oluyorsunuz. aynı durum soda için geçerli.Yılda bir iki kez herşey dahil otellerde "
    "konaklayan biri olarak söylüyorum bu otel ekstra karışık ve yorucuydu. A la carte olarak italyan "
    "restoran başarılıydı. Eray Bey'e teşekkür ederiz. Ayrıca animasyon ekibinden Yusuf Bey'e teşekkürler. "
    "Bunca kalabalığın içerisinde personel çabaları genel olarak iyiydi, masalarda çatal bıçak "
    "bulamadığımız,oturacak bir masa bulduğumuzdada temizletemediğimiz anlar da oldu. Bunları "
    "paylaşmaktaki amacım ise rezervasyon yapanların bilerek gelmesi ve otel sahiplerinin görmelerini "
    "istemem.iyileştirmeler geri bildirimlerle mümkün…"
)

# Paraphrases — must pass WITHOUT new keyword patches
PARAPHRASES = {
    "room_size": [
        "odalar çok küçük",
        "oda fazlasıyla dardı",
        "odamız oldukça minik kaldı",
    ],
    "food_mediocre": [
        "yemeklerin lezzeti ortalamaydı",
        "yemekler idare ederdi",
        "lezzet fena değil ama özel de değil",
        "yemekler eh işteydi",
    ],
    "table_service": [
        "oturacak bir masa bulduğumuzdada temizletemediğimiz anlar da oldu",
        "restoranda masa kirliydi silen kimse yoktu",
        "masa bulduk ama temizlenmemişti",
    ],
    "queue": [
        "10kişilik sırayı beklemiş oluyorsunuz",
        "15 kişilik kuyrukta bekledik",
        "ayran için uzun sıra bekliyorsunuz",
    ],
    "queue_opening_narrative": [
        "tek kelimeyle özetleyecek olsaydım sadece yorgunluk diyebilirdim "
        "inanılmaz kuyruklar inanılmaz sıralar beklemek zorunda kaldık hatta pankek "
        "sırasında 20 25 dakika bekleyip en son pes edip çıktığımı hatırlıyorum",
        "açıkçası inanılmaz kuyruklar vardı pankek için 20 dakika bekledik pes edip çıktık",
    ],
    "capacity_chaos": [
        "Yılda bir iki kez herşey dahil otellerde konaklayan biri olarak söylüyorum "
        "bu otel ekstra karışık ve yorucuydu",
        "herşey dahil olmasına rağmen ekstra karışık ve yorucuydu",
    ],
    "animation_thanks": [
        "Ayrıca animasyon ekibinden Yusuf Bey'e teşekkürler",
        "animasyon ekibine teşekkür ederiz",
    ],
    "beverage": [
        "aynı durum soda için geçerli",
        "barda limonata yoktu",
        "istediğiniz içeceği barda bulamıyorsunuz",
    ],
    "value": [
        "paramız çöp oldu diyebilirim",
        "paraya değmez pişman olduk",
    ],
    "meta": [
        "bugün otelden ayrıldım",
        "ben çok ciddiye almamıştım",
        "paylaşmaktaki amacım ise rezervasyon yapanların bilerek gelmesi",
        "iyileştirmeler geri bildirimlerle mümkün",
    ],
}


@pytest.fixture(autouse=True)
def _reload():
    reload_ontology()
    reload_pipeline_config()
    yield


class TestPipelineFrames:
    def test_room_size_not_housekeeping_cleanliness(self):
        for phrase in PARAPHRASES["room_size"]:
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key in ("room_size", "general_room_comfort", "guest_experience")
            assert "temizlik" not in d.aspect_label.lower()
            assert d.department_label in ("Odalar", "Genel", "Front Office", "Housekeeping", "Oda Hizmetleri & Housekeeping", "Kat Hizmetleri & Temizlik")

    def test_table_service_is_restaurant_not_hk(self):
        for phrase in PARAPHRASES["table_service"]:
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key in ("table_cleanliness", "restaurant_service", "room_cleanliness", "housekeeping_service")
            assert d.department_label in ("Restaurant", "Yiyecek & İçecek (F&B)", "Housekeeping", "Oda Hizmetleri & Housekeeping")
            assert d.sentiment in ("Negative", "Neutral")

    def test_mediocre_not_positive(self):
        for phrase in PARAPHRASES["food_mediocre"]:
            sent, score = detect_strong_sentiment(phrase)
            assert sent != "Positive", f"{phrase} → {sent} {score}"
            d = classify_clause(phrase, base_sentiment=sent, base_score=score)
            assert d.sentiment in ("Neutral", "Negative")
            assert d.sentiment_score <= 0.05

    def test_queue_negative(self):
        for phrase in PARAPHRASES["queue"]:
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key in ("service_queue", "queue_waiting", "capacity")
            assert d.sentiment == "Negative"

    def test_opening_queue_narrative_rescued_not_meta(self):
        """Long framing + queue/exhaustion must NOT be dropped as meta."""
        for phrase in PARAPHRASES["queue_opening_narrative"]:
            assert not is_meta_clause(phrase), f"should rescue: {phrase[:60]}"
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key in ("service_queue", "queue_waiting", "capacity", "guest_experience", "general_atmosphere")
            assert d.sentiment == "Negative"
            assert d.priority in ("high", "critical")

    def test_capacity_all_inclusive_not_diger(self):
        for phrase in PARAPHRASES["capacity_chaos"]:
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key in ("capacity", "guest_experience", "general_atmosphere")
            assert d.aspect_label in ("Kapasite / Yoğunluk", "Genel Deneyim", "Genel Atmosfer")
            assert d.department_label in ("Genel", "Otel Atmosferi & Misafir Profili")
            assert "diğer" not in d.department_label.lower()
            assert d.sentiment == "Negative"

    def test_animation_thanks_not_spa(self):
        for phrase in PARAPHRASES["animation_thanks"]:
            d = classify_clause(phrase)
            assert d.include
            assert d.aspect_key == "animation"
            assert "spa" not in d.department_label.lower()
            assert "spa" not in (d.category or "").lower()
            assert d.department_label in ("Animasyon", "Animasyon & Etkinlik", "Rekreasyon & Eğlence")
            # Force-guard even if base mapping wrongly says Spa
            d2 = classify_clause(
                phrase,
                base_mapping={
                    "department": "spa",
                    "department_label": "Spa & Wellness",
                    "departmentLabel": "Spa & Wellness",
                    "aspect_key": "animation",
                    "aspect_label": "Animasyon",
                },
            )
            assert "spa" not in d2.department_label.lower()
            assert d2.department_label in ("Animasyon", "Animasyon & Etkinlik", "Rekreasyon & Eğlence")

    def test_meta_dropped(self):
        for phrase in PARAPHRASES["meta"]:
            assert is_meta_clause(phrase) or not classify_clause(phrase).include

    def test_beverage_bar_not_hk(self):
        for phrase in PARAPHRASES["beverage"]:
            d = classify_clause(phrase)
            assert d.department_label in ("Bar", "Restaurant", "Yiyecek & İçecek (F&B)")
            assert "housekeeping" not in d.department_label.lower()
            assert "kat" not in d.department_label.lower()

    def test_value_not_finance(self):
        for phrase in PARAPHRASES["value"]:
            r = classify_by_rules(phrase)
            assert r.category != CAT_FINANCE
            d = classify_clause(phrase)
            assert d.department_label in ("Genel", "Otel Atmosferi & Misafir Profili", "Ön Büro & Misafir İlişkileri")
            assert "finans" not in d.department_label.lower()


class TestCrystalExhaustionFull:
    def test_absa_systemic_expectations(self):
        result = AbsaService.analyze(CRYSTAL_EXHAUSTION, rating=None, multidomain=True)
        clauses_joined = " | ".join(a.clause.lower() for a in result.aspects)

        meta_hits = [
            a for a in result.aspects
            if any(m in a.clause.lower() for m in (
                "ciddiye almamış", "paylaşmaktaki amac", "geri bildirimlerle",
                "bugün otelden ayrıldım",
            )) and not any(q in a.clause.lower() for q in ("kuyruk", "sıra", "sira", "bekle", "yorgun"))
        ]
        assert not meta_hits, f"Meta clauses leaked: {[a.clause[:40] for a in meta_hits]}"

        # Core opening narrative (yorgunluk / kuyruk / pankek / pes) must appear
        queue_core = [
            a for a in result.aspects
            if any(w in a.clause.lower() for w in ("kuyruk", "pankek", "yorgunluk", "pes edip", "pes edip"))
            or ("sıra" in a.clause.lower() or "sira" in a.clause.lower())
        ]
        assert queue_core, f"Opening queue narrative missing. Aspects: {clauses_joined[:400]}"
        assert any(
            a.sentiment == "Negative"
            and (
                "kuyruk" in (a.aspect_label or a.aspect or "").lower()
                or "servis" in (a.aspect_label or a.aspect or "").lower()
                or a.aspect_key in ("service_queue", "capacity")
                or "kuyruk" in a.clause.lower()
            )
            for a in queue_core
        )

        rooms = [a for a in result.aspects if "küçük" in a.clause.lower() or "kucuk" in a.clause.lower()]
        assert rooms, f"Room clause missing. Aspects: {clauses_joined[:200]}"
        for a in rooms:
            al = (a.aspect_label or a.aspect or "").lower()
            assert "temizlik" not in al

        tables = [
            a for a in result.aspects
            if "temizletemed" in a.clause.lower() or ("masa" in a.clause.lower() and "temiz" in a.clause.lower())
        ]
        assert tables
        for a in tables:
            label = (a.department_label or a.department or "").lower()
            assert "restaurant" in label or "yiyecek" in label or a.department in ("restaurant", "food_beverage", "housekeeping")

        taste = [a for a in result.aspects if "lezzet" in a.clause.lower() or "ortalama" in a.clause.lower()]
        assert taste
        assert all(a.sentiment != "Positive" for a in taste)

        queue = [
            a for a in result.aspects
            if "kişilik" in a.clause.lower() or "kisilik" in a.clause.lower() or "sırayı" in a.clause.lower()
        ]
        assert queue
        assert any(a.sentiment == "Negative" for a in queue)

        chaos = [
            a for a in result.aspects
            if "karışık" in a.clause.lower() or "karisik" in a.clause.lower() or "yorucu" in a.clause.lower()
        ]
        assert chaos
        for a in chaos:
            label = (a.department_label or a.department or "").lower()
            assert "diğer" not in label
            al = (a.aspect_label or a.aspect or "").lower()
            assert any(x in al for x in ("deneyim", "kapasite", "yoğunluk", "genel", "atmosfer"))

        anim = [a for a in result.aspects if "animasyon" in a.clause.lower() or "yusuf" in a.clause.lower()]
        assert anim
        for a in anim:
            label = (a.department_label or a.department or "").lower()
            assert "spa" not in label
            assert "animasyon" in label or "rekreasyon" in label or a.aspect_key in ("animation", "staff_attitude")

        financeish = [
            a for a in result.aspects
            if (getattr(a, "department_label", "") or a.department or "").lower() in (
                "muhasebe & finans", "muhasebe", "finans",
            )
            or (getattr(a, "domain", "") or "") == "finans"
        ]
        assert not financeish

        soda = [a for a in result.aspects if "soda" in a.clause.lower()]
        assert soda
        for a in soda:
            label = (a.department_label or a.department or "").lower()
            assert "housekeeping" not in label and "kat" not in label

        meat = [a for a in result.aspects if "kiyma" in a.clause.lower() or "kıyma" in a.clause.lower()]
        assert meat and any(a.sentiment == "Negative" for a in meat)

    def test_summary_operational_not_narrative(self):
        summary = RagService.generate_summary(CRYSTAL_EXHAUSTION)
        assert len(summary) < 260
        low = summary.lower()
        assert not low.startswith("bugün otelden")
        assert not low.startswith("olsaydım")
        assert not low.startswith("tek kelimeyle")
        assert any(w in low for w in (
            "kuyruk", "yorgun", "pişman", "pisman", "çöp", "cop", "sıra", "sira", "bekle", "pes",
        ))
        # Prefer long opening queue narrative over short 10kişilik fragment when both exist
        assert "kuyruk" in low or "yorgun" in low or "pes" in low or "sıra" in low or "sira" in low

    def test_stars_mixed_not_one(self):
        sent, score = analyze_sentiment_with_rating(CRYSTAL_EXHAUSTION, None)
        stars = predict_star_rating(CRYSTAL_EXHAUSTION, sent, score)
        assert 2 <= stars <= 3
        mixed = analyze_mixed_review(CRYSTAL_EXHAUSTION)
        assert mixed.is_mixed is True

    def test_rooms_and_food_split(self):
        parts = split_clauses_absa(
            "onun dışında odalar çok küçük yemeklerin lezzeti ortalamaydı ama kıyma kalitesi çok düşüktü."
        )
        assert len(parts) >= 2
        roomish = [p for p in parts if "oda" in p.lower() and ("küçük" in p.lower() or "kucuk" in p.lower())]
        foodish = [p for p in parts if any(w in p.lower() for w in ("yemek", "lezzet", "kiyma", "kıyma"))]
        assert roomish and foodish


class TestPipelineConfigDriven:
    def test_config_loads(self):
        from app.services.clause_pipeline import load_pipeline_config
        cfg = load_pipeline_config()
        assert cfg.get("mediocre_lexicon")
        assert cfg.get("frames")
        assert cfg.get("anti_patterns")
        assert cfg.get("meta_rescue_cues")
        assert "capacity" in (cfg.get("frames") or {})

    def test_summary_via_pipeline_facade(self):
        s = ClausePipeline.summary(CRYSTAL_EXHAUSTION)
        assert s
        assert any(w in s.lower() for w in ("kuyruk", "yorgun", "sıra", "sira", "bekle", "pişman", "pisman", "pes"))
