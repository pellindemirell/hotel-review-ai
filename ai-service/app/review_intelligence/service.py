"""Public API for Review Intelligence Engine — standalone service boundary."""

from __future__ import annotations

from typing import Any, Optional

from app.review_intelligence.models import ReviewIntelligenceResult
from app.review_intelligence.pipeline import ReviewIntelligencePipeline


class ReviewIntelligenceService:
    """
    Commercial-grade Review Intelligence API (DOC-004).
    Separable service boundary for future standalone product.
    """

    def __init__(self) -> None:
        self._pipeline = ReviewIntelligencePipeline()

    def analyze(
        self,
        review_text: str,
        review_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        language: str | None = None,
        rating: int | None = None,
    ) -> ReviewIntelligenceResult:
        return self._pipeline.run(
            review_text=review_text,
            review_id=review_id,
            metadata=metadata,
            language=language,
            rating=rating,
        )

    def analyze_batch(
        self,
        reviews: list[str],
        metadata_list: list[dict[str, Any]] | None = None,
    ) -> list[ReviewIntelligenceResult]:
        meta_list = metadata_list or [{} for _ in range(len(reviews))]
        results: list[ReviewIntelligenceResult] = []
        for i, text in enumerate(reviews):
            meta = meta_list[i] if i < len(meta_list) else {}
            results.append(self.analyze(text, metadata=meta))
        return results
