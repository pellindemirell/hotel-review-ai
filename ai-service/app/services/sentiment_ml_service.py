import os
import logging
import joblib
from typing import Optional

from app.services.turkish_nlp_utils import analyze_sentiment_with_rating

logger = logging.getLogger("ai_service")


class SentimentMLService:
    """Rule-based sentiment with ML augmentation when beneficial.
    Kept as a thin wrapper to preserve API compatibility."""

    def analyze(self, text: str, rating: Optional[int] = None) -> tuple[str, float]:
        return analyze_sentiment_with_rating(text, rating)
