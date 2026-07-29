from typing import Optional

from app.services.turkish_nlp_utils import (
    analyze_sentiment_with_rating,
    detect_manipulation,
    detect_strong_sentiment,
    predict_star_rating,
)
from app.services.sentiment_ml_service import SentimentMLService


class SentimentService:
    """ML-öncelikli duygu analizi servisi. Düşük güvende kural tabanlına düşer."""

    POSITIVE_WORDS = None
    NEGATIVE_WORDS = None

    _ml_service = SentimentMLService()

    @classmethod
    def predict_rating(cls, text: str, sentiment: str, sentiment_score: float) -> int:
        return predict_star_rating(text, sentiment, sentiment_score)

    @classmethod
    def is_manipulation(cls, text: str, rating: Optional[int] = None) -> bool:
        return detect_manipulation(text, rating)

    @classmethod
    def analyze_sentiment(cls, text: str, rating: Optional[int] = None) -> tuple[str, float]:
        sent, score = cls._ml_service.analyze(text, rating)
        return sent, score

    @classmethod
    def detect_sentiment(cls, text: str) -> tuple[str, float]:
        return detect_strong_sentiment(text)
