from typing import Optional

from app.services.turkish_nlp_utils import (
    analyze_sentiment_with_rating,
    detect_manipulation,
    detect_strong_sentiment,
    predict_star_rating,
)


class SentimentService:
    """Duygu analizi servisi — merkezi turkish_nlp_utils sarmalayıcısı."""

    @classmethod
    def predict_rating(cls, text: str, sentiment: str, sentiment_score: float) -> int:
        return predict_star_rating(text, sentiment, sentiment_score)

    @classmethod
    def is_manipulation(cls, text: str, rating: Optional[int] = None) -> bool:
        return detect_manipulation(text, rating)

    @classmethod
    def analyze_sentiment(cls, text: str, rating: Optional[int] = None) -> tuple[str, float]:
        return analyze_sentiment_with_rating(text, rating)

    @classmethod
    def detect_sentiment(cls, text: str) -> tuple[str, float]:
        return detect_strong_sentiment(text)
