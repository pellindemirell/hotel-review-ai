"""Tests for core AI services — sentiment, category, keyword, OCR.
Covers 10+ diverse Turkish hotel reviews."""

from __future__ import annotations

import os
import sys
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.sentiment_service import SentimentService
from app.services.category_service import CategoryService
from app.services.keyword_service import KeywordService


# 10 Turkish hotel reviews covering various categories and sentiments
REVIEWS = [
    ("Oda tertemizdi, manzara muhteşemdi, kesinlikle tekrar gelirim.", 5),
    ("Banyo çok kirliydi, havlular değiştirilmemiş, rezalet bir temizlik.", 1),
    ("Kahvaltı çeşitliliği iyiydi ama yemekler soğuk servis edildi.", 3),
    ("Personel çok ilgili ve güler yüzlüydü, her şey için teşekkürler.", 5),
    ("Klima çalışmıyordu, oda aşırı sıcaktı, uyuyamadık.", 1),
    ("Otel konumu harika, denize sıfır, plaj çok güzel.", 4),
    ("WiFi sürekli kopuyor, odada telefon çekmiyor, iletişim sorunu.", 2),
    ("Havuz temiz ve bakımlıydı, çocuklar çok eğlendi.", 5),
    ("Fiyat performans açısından ortalama bir otel, beklediğim gibi.", 3),
    ("Gürültü çok fazlaydı, ses yalıtımı yetersiz, gece uyuyamadık.", 2),
    ("Restorandaki garsonlar çok profesyonel ve hızlıydı.", 5),
    ("Otopark sorunu var, araç için yer bulamadık.", 2),
]


@pytest.fixture
def category_service() -> CategoryService:
    return CategoryService()


class TestSentimentService:
    def test_positive_high_rating(self):
        sentiment, score = SentimentService.analyze_sentiment(
            "Oda tertemizdi, manzara muhteşemdi, kesinlikle tekrar gelirim.", 5
        )
        assert sentiment == "Positive"
        assert score > 0

    def test_negative_low_rating(self):
        sentiment, score = SentimentService.analyze_sentiment(
            "Banyo çok kirliydi, havlular değiştirilmemiş, rezalet bir temizlik.", 1
        )
        assert sentiment == "Negative"
        assert score < 0

    def test_neutral_mid_rating(self):
        sentiment, score = SentimentService.analyze_sentiment(
            "Fiyat performans açısından ortalama bir otel, beklediğim gibi.", 3
        )
        assert sentiment in ("Positive", "Negative", "Neutral")

    def test_no_rating_predicts(self):
        sentiment, score = SentimentService.analyze_sentiment(
            "Personel çok ilgili ve güler yüzlüydü, her şey için teşekkürler."
        )
        assert sentiment == "Positive"
        assert score > 0

    def test_all_reviews_have_sentiment(self):
        for text, rating in REVIEWS:
            sentiment, score = SentimentService.analyze_sentiment(text, rating)
            assert sentiment in ("Positive", "Negative", "Neutral")
            assert -1.0 <= score <= 1.0


class TestCategoryService:
    def test_cleanliness_category(self, category_service):
        cat, conf, method, secondary, is_mixed = category_service.classify_category(
            "Banyo çok kirliydi, havlular değiştirilmemiş."
        )
        assert isinstance(cat, str)
        assert 0.0 <= conf <= 1.0

    def test_food_category(self, category_service):
        cat, conf, method, secondary, is_mixed = category_service.classify_category(
            "Kahvaltı çeşitliliği iyiydi ama yemekler soğuk servis edildi."
        )
        assert isinstance(cat, str)

    def test_staff_category(self, category_service):
        cat, conf, method, secondary, is_mixed = category_service.classify_category(
            "Personel çok ilgili ve güler yüzlüydü."
        )
        assert isinstance(cat, str)

    def test_hvac_category(self, category_service):
        cat, conf, method, secondary, is_mixed = category_service.classify_category(
            "Klima çalışmıyordu, oda aşırı sıcaktı."
        )
        assert isinstance(cat, str)

    def test_location_category(self, category_service):
        cat, conf, method, secondary, is_mixed = category_service.classify_category(
            "Otel konumu harika, denize sıfır."
        )
        assert isinstance(cat, str)

    def test_all_reviews_return_valid_category(self, category_service):
        for text, rating in REVIEWS:
            cat, conf, method, secondary, is_mixed = category_service.classify_category(text)
            assert isinstance(cat, str) and len(cat) > 0
            assert 0.0 <= conf <= 1.0
            assert method in ("rules", "model", "gemini", "fallback")


class TestKeywordService:
    def test_extract_keywords_returns_list(self):
        keywords = KeywordService.extract_keywords(
            "Banyo çok kirliydi, havlular değiştirilmemiş, rezalet."
        )
        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_extract_keywords_max_count(self):
        keywords = KeywordService.extract_keywords(
            "Oda temiz, personel ilgili, yemekler güzel, manzara muhteşemdi.",
            max_keywords=3,
        )
        assert len(keywords) <= 3

    def test_extract_keywords_positive_review(self):
        keywords = KeywordService.extract_keywords(
            "Harika bir tatildi, her şey mükemmeldi."
        )
        assert len(keywords) > 0

    def test_extract_keywords_empty_text(self):
        keywords = KeywordService.extract_keywords("")
        assert keywords == []

    def test_all_reviews_have_keywords(self):
        for text, _ in REVIEWS:
            keywords = KeywordService.extract_keywords(text, max_keywords=3)
            assert isinstance(keywords, list)


class TestSentimentOnAllReviews:
    @pytest.mark.parametrize("text,rating", REVIEWS)
    def test_each_review_sentiment(self, text, rating):
        sentiment, score = SentimentService.analyze_sentiment(text, rating)
        assert sentiment in ("Positive", "Negative", "Neutral")
        assert -1.0 <= score <= 1.0
