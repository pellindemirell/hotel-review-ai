"""Temel scraper adaptör arayüzü."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.review_ingestion_schema import IngestedReview


@dataclass
class AdapterResult:
    reviews: list[IngestedReview] = field(default_factory=list)
    warning: Optional[str] = None
    error: Optional[str] = None
    method: str = ""
    legal_notice: str = ""

    @property
    def success(self) -> bool:
        return bool(self.reviews) and not self.error


class BaseScraperAdapter(ABC):
    """Her platform adaptörü bu arayüzü uygular."""

    source_id: str = "unknown"
    display_name: str = "Unknown"

    @abstractmethod
    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        """Yorumları çek ve IngestedReview listesi döndür."""
        ...

    @abstractmethod
    def legal_info(self) -> dict[str, Any]:
        """Yasal durum ve önerilen kullanım."""
        ...

    def _make_review(
        self,
        comment: str,
        *,
        hotel: str = "",
        country: str = "",
        city: str = "",
        platform: str = "",
        rating: float = 0.0,
        guest_name: str = "Anonim",
        title: str = "",
        date: str = "",
        language: str = "",
        traveler_type: str = "",
        room_type: str = "",
        stay_duration: str = "",
        trip_purpose: str = "",
        positive_text: str = "",
        negative_text: str = "",
        helpful_count: int = 0,
        is_most_helpful: bool = False,
        review_id: str = "",
        source_url: str = "",
        ingestion_method: str = "",
        legal_notice: str = "",
    ) -> IngestedReview:
        review = IngestedReview(
            hotel=hotel,
            country=country,
            city=city,
            language=language,
            platform=platform or self.display_name,
            date=date,
            rating=rating,
            title=title,
            comment=comment,
            traveler_type=traveler_type,
            room_type=room_type,
            stay_duration=stay_duration,
            trip_purpose=trip_purpose,
            positive_text=positive_text,
            negative_text=negative_text,
            guest_name=guest_name,
            helpful_count=helpful_count,
            is_most_helpful=is_most_helpful,
            review_id=review_id,
            source_url=source_url,
            ingestion_method=ingestion_method or self.source_id,
            legal_notice=legal_notice,
        )
        return review.ensure_hash()
