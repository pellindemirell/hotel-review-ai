"""Aspect-based sentiment — wraps AbsaService + ontology per-clause analysis."""

from __future__ import annotations

from typing import Optional

from app.review_intelligence.models import SentimentInfo
from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.sentiment_service import SentimentService
from app.services.turkish_nlp_utils import detect_strong_sentiment
from app.ontology.engine import get_hotel_ontology_engine


class SentimentEngine:
    """Stage 9: Aspect-based sentiment (NOT document-level only)."""

    def analyze_clause(
        self,
        clause: str,
        full_text: str = "",
        rating: Optional[int] = None,
    ) -> SentimentInfo:
        engine = get_hotel_ontology_engine()
        ontology_sent = engine._detect_sentiment(clause)

        sentiment, score = SentimentService.analyze_sentiment(clause, rating=None)
        if sentiment == "Neutral":
            sentiment, score = detect_strong_sentiment(clause)

        # Ontology lexicon override for strong signals
        if ontology_sent == "positive" and sentiment != "Positive":
            if score < 0.55:
                sentiment, score = "Positive", max(score, 0.65)
        elif ontology_sent == "negative" and sentiment != "Negative":
            if score > -0.55:
                sentiment, score = "Negative", min(score, -0.65)

        return SentimentInfo(
            label=sentiment,
            score=score,
            aspect_based=True,
        )

    def analyze_document(
        self,
        text: str,
        rating: Optional[int] = None,
    ) -> tuple[str, float, bool]:
        """Return overall sentiment, score, is_mixed."""
        clauses = split_clauses_absa(text)
        if not clauses:
            clauses = [text]

        labels = [self.analyze_clause(c, text, rating).label for c in clauses]
        pos = labels.count("Positive")
        neg = labels.count("Negative")
        is_mixed = pos > 0 and neg > 0

        if is_mixed:
            overall = "Mixed"
        elif neg > pos:
            overall = "Negative"
        elif pos > neg:
            overall = "Positive"
        else:
            overall, score = SentimentService.analyze_sentiment(text, rating)
            return overall, score, False

        result = AbsaService.analyze(text, rating=rating)
        return overall, result.overall_score, is_mixed
