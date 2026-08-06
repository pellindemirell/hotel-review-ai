"""Regression: uzun karışık Crystal-style otel yorumu.

Beklenen:
- Birincil kategori Yiyecek & İçecek (Diğer değil)
- Duygu karışık/nötr (net Positive 0.35 değil)
- Yıldız ≤ 4 (5 değil)
- ABSA: aquapark→Spa/Havuz; meyve/şarap→F&B; az KRİTİK; Diğer baskın olmasın
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.absa_service import AbsaService
from app.services.category_rules import classify_by_rules
from app.services.turkish_nlp_utils import (
    CAT_FOOD,
    CAT_OTHER,
    CAT_SPA,
    analyze_mixed_review,
    analyze_sentiment_with_rating,
    predict_star_rating,
)

CRYSTAL_MIXED_REVIEW = (
    "Odalar daha bakımlı hale getirilebilir, özellikle banyo. "
    "Hijyen açısından bir sorun görmedim genel olarak temizdi. "
    "Etkinlikler de olması gerektiği gibi güzeldi. "
    "Haziran 2. Haftası itibariyle genel olarak yoğun değildi istediğiniz şeye beklemeden erişebiliyorsunuz. "
    "Çalışanlar genel olarak kibardı. "
    "Otelin en büyük eksiği bu fiyattaki bir otelde mini barı çok yetersiz sadece alkolsüz içecek var "
    "ve hiçbir yiyecek yok.(en azından kutu bira ve ufak atıştırmalık konabilir). "
    "Ara sıcak saatlerindeki hamburger gözleme kızartma tarzı yiyecekler güzel ve yeterli. "
    "Kahvaltı ve akşam yemeklerindeki çeşitlilik daha iyi olabilir örneğin mevsimi olmasına rağmen "
    "kavun, çilek ve kiraz gibi meyveler hiç çıkmadı. "
    "Kahvaltı da çeşitlilik yetersiz örneğin bal kaymak bitiyor. "
    "Bu söylediklerim çeşitlendirilebilir. "
    "Akşam yemeklerinde ikram edilen rakı ve şaraplar bence kalitesiz 2. sınıf ürünlerdi. "
    "Dondurma sadece pastanede var belki plajda varsa ben görmemiş olabilirim, "
    "bardakta veriliyor külah veya paket dondurma olmaması negatif. "
    "Yemekler; kahvaltı ara sıcakalar ve akşam yemeği genel olarak iyi ama çeşitlilik arttırılmalı. "
    "3 aquaprk var 1'i kapalıydı ama 2'si yeterliydi çok aşırı sıra beklemiyorsunuz "
    "ancak bir tanesinin ciddi bakıma ihtiyacı var. "
    "En üst bölgede yer alan demirler oldukça yıpranmış duruyor. "
    "Plaj çakıl ve çok çabuk derinleşiyor belli bir yerden sonra kum. "
    "Kitle, genelde çocuklu aileler ve belli bir yaş üstü kişiler. "
    "Bir daha olsa gelir miyim bu eksiklikler tamamlanırsa gelinir. "
    "5 gece 6 gün tatilin son gününde yazıyorum."
)


class TestCrystalMixedReviewRegression:
    def test_mixed_primary_is_food_not_other(self):
        mixed = analyze_mixed_review(CRYSTAL_MIXED_REVIEW)
        assert mixed.is_mixed is True
        assert mixed.primary_category == CAT_FOOD
        assert mixed.primary_category != CAT_OTHER
        assert mixed.overall_sentiment in ("Neutral", "Negative")
        assert not (
            mixed.overall_sentiment == "Positive" and abs((mixed.overall_score or 0) - 0.35) < 0.01
        )

    def test_rules_classify_food(self):
        result = classify_by_rules(CRYSTAL_MIXED_REVIEW)
        assert result.category == CAT_FOOD
        assert result.is_mixed is True
        assert result.confidence >= 0.85

    def test_sentiment_and_stars_not_inflated(self):
        sent, score = analyze_sentiment_with_rating(CRYSTAL_MIXED_REVIEW, None)
        assert sent in ("Neutral", "Negative")
        stars = predict_star_rating(CRYSTAL_MIXED_REVIEW, sent, score)
        assert stars <= 4
        assert stars != 5

    def test_light_absa_departments(self):
        result = AbsaService.analyze(CRYSTAL_MIXED_REVIEW, rating=None, multidomain=False)
        assert result.is_multi_aspect is True
        assert len(result.aspects) >= 5

        other_count = sum(
            1 for a in result.aspects
            if a.department in (CAT_OTHER, "Diğer", "Genel") or a.department_label in ("Diğer", "Genel")
        )
        food_count = sum(
            1 for a in result.aspects
            if a.department in (CAT_FOOD, "food_beverage", "Yiyecek & İçecek (F&B)", "Yiyecek & İçecek & Yemekler")
            or a.department_label in ("Yiyecek & İçecek (F&B)", "Yiyecek & İçecek & Yemekler")
        )
        assert food_count >= 3
        assert other_count < food_count

        critical = [a for a in result.aspects if a.priority == "critical"]
        assert len(critical) <= max(3, len(result.aspects) // 5)

        aqua = [
            a for a in result.aspects
            if "aquaprk" in a.clause.lower() or "aquapark" in a.clause.lower()
        ]
        assert aqua, "Aquapark cümleciği bekleniyor"
        for a in aqua:
            assert a.department in (CAT_SPA, "leisure", "Rekreasyon & Eğlence", "Havuz & Aktivite"), f"aquapark → Spa/Rekreasyon beklenirdi, alınan: {a.department} ({a.clause})"

        fruit_wine = [
            a for a in result.aspects
            if any(w in a.clause.lower() for w in ("meyve", "şarap", "sarap", "rakı", "raki"))
        ]
        assert fruit_wine, "Meyve/şarap cümlecik bekleniyor"
        for a in fruit_wine:
            assert a.department in (CAT_FOOD, "food_beverage", "Yiyecek & İçecek (F&B)", "Yiyecek & İçecek & Yemekler"), f"meyve/şarap → F&B beklenirdi: {a.department} ({a.clause})"
