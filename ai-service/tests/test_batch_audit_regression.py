"""Regression tests from HotelRec 200-review batch audit systemic flags."""
from __future__ import annotations

import pytest

from app.services.clause_pipeline import classify_clause, reload_pipeline_config, _fold


@pytest.fixture(autouse=True)
def _reload_cfg():
    reload_pipeline_config()


class TestPraiseWrongSentiment:
    def test_wifi_harika_positive(self):
        d = classify_clause("wifi harika, bağlantı sorunu yok")
        assert d.sentiment == "Positive"
        assert d.sentiment_score >= 0.5
        assert d.aspect_key == "wifi"

    def test_harika_degil_stays_negative(self):
        d = classify_clause("harika değil, otel berbat")
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0

    def test_walkability_praise_not_forced_negative(self):
        d = classify_clause(
            "konumu mükemmel, tüm ana mekanlara yürüme mesafesinde, havaalanına giden otobüs hattı üzerinde"
        )
        assert d.aspect_key == "property_walkability"
        assert d.sentiment == "Positive"
        assert d.sentiment_score > 0

    def test_otel_harika_walk_distance_positive(self):
        d = classify_clause(
            "şehir merkezine ve kaleye yürüme mesafesinde bir otel arıyorsanız bu otel harika"
        )
        assert d.aspect_key == "property_walkability"
        assert d.sentiment == "Positive"

    def test_combining_diacritic_harika_positive(self):
        # Soft-dotted i (U+0307) as seen in HotelRec OCR/normalize artifacts
        clause = "her şeyden hari\u0307ka bi\u0307r konaklama"
        assert "harika" in _fold(clause)
        d = classify_clause(clause)
        assert d.sentiment == "Positive"

    def test_short_walk_guzel_positive(self):
        d = classify_clause("alışveriş merkezine yürüme mesafesinde güzel")
        assert d.aspect_key == "property_walkability"
        assert d.sentiment == "Positive"


class TestPricingAsTaste:
    def test_ekstra_euro_breakfast_is_extra_charge(self):
        d = classify_clause(
            "ücretsiz wi-fi ve kişi başı ekstra 12,00 euro ödemeniz gereken iyi bir kahvaltı"
        )
        assert d.aspect_key == "fb_extra_charge"
        assert d.aspect_key != "food_taste"
        assert "lezzet" not in (d.aspect_label or "").lower()
        assert d.sentiment == "Negative"

    def test_ucretsiz_kahvalti_not_forced_extra_charge(self):
        """Bare free breakfast praise is not a pricing complaint."""
        d = classify_clause("yakındaki restoranda ücretsiz wifi ve kahvaltı iyiydi")
        assert d.aspect_key != "fb_extra_charge"


class TestWalkVsQueue:
    def test_havuz_deniz_walk_not_fb_queue(self):
        d = classify_clause(
            "Su kaydıraklarının oradaki havuzdan denize yürümek bile uzun sürüyor."
        )
        # Layout/walk complaint: property_walkability or beach — never F&B/pool queue
        assert d.aspect_key in ("property_walkability", "beach", "location", "guest_experience")
        assert d.aspect_key not in ("service_queue", "pool_queue", "food_queue")
        assert d.sentiment == "Negative"

    def test_server_wait_not_pool_queue(self):
        d = classify_clause(
            "2 saat yerde kaldım ve bir sunucunun benimle iletişim kurmasını sağladım"
        )
        assert d.aspect_key != "pool_queue"
        assert d.aspect_key in ("service_queue", "guest_experience", "staff_behavior", "general")


class TestLeftoverAuditFalsePositives:
    """Original leftover praise_wrong_sentiment flags — sentiment OK; aspect must not misfire."""

    def test_kalbim_batti_stays_negative_not_room_size(self):
        # Expectation→disappointment narrative; "küçük bir mola" must not force room_size
        d = classify_clause(
            "eşim ve ben merkezi bir nokta için otel rezervasyonu yaptık, çünkü küçük bir mola için "
            "tüm sitelerdeki tüm güzel resimleri gördüm, bu yüzden harika görünüyordu, otele yaklaşırken "
            "kalbim battı, kesinlikle resimlere benzemeyen"
        )
        assert d.sentiment == "Negative"
        assert d.sentiment_score < 0
        assert d.aspect_key != "room_size"

    def test_kucuk_bir_mola_not_room_size(self):
        d = classify_clause("küçük bir mola")
        assert d.aspect_key != "room_size"

    def test_yosemite_uzun_dag_not_service_queue(self):
        # Bare "uzun" in travel context ≠ F&B queue
        d = classify_clause(
            "yosemite'e yapacağınız uzun dağ yolculuğundan önce güzel bir gece uykusu çekmek istiyordum"
        )
        assert d.aspect_key not in ("service_queue", "pool_queue", "food_queue")
        assert d.sentiment != "Positive"  # intention/wish, not delivered praise

    def test_uzun_sira_still_queue(self):
        d = classify_clause("bardaki uzun sıra yüzünden içecek alınamıyor")
        assert d.aspect_key == "service_queue"
        assert d.aspect_key not in ("general", "food_taste", "property_walkability")

