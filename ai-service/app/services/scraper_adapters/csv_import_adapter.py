"""Evrensel CSV import adaptörü — herhangi bir platform export'u."""
from __future__ import annotations

import csv
import os
from typing import Any

from app.services.review_ingestion_schema import normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter

# Standart sütun alias'ları
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "comment": ("comment", "original_comment", "text", "review", "yorum", "review_text", "review_body", "content"),
    "rating": ("rating", "puan", "stars", "score", "review_score"),
    "guest_name": ("guest_name", "author", "misafir", "reviewer_name", "reviewer", "name", "user"),
    "date": ("review_date", "date", "created_at", "published_date", "review_time"),
    "title": ("title", "review_title", "headline", "subject"),
    "platform": ("source", "platform", "site", "website"),
    "language": ("language", "lang", "locale"),
    "hotel": ("hotel", "hotel_name", "property_name", "otel"),
    "city": ("city", "sehir", "location_city"),
    "country": ("country", "ulke", "location_country"),
    "traveler_type": ("traveler_type", "traveller_type", "guest_type"),
    "room_type": ("room_type", "room", "oda_tipi"),
    "stay_duration": ("stay_duration", "nights", "duration", "gece"),
    "trip_purpose": ("trip_purpose", "trip_type", "purpose", "seyahat_amaci", "stay_type"),
    "positive_text": ("positive_text", "pros", "positive", "liked", "positives"),
    "negative_text": ("negative_text", "cons", "negative", "disliked", "negatives"),
    "helpful_count": ("helpful_count", "helpful", "likes", "thumbs_up", "vote_count"),
    "is_most_helpful": ("is_most_helpful", "most_helpful", "top_review", "featured"),
}


class CsvImportAdapter(BaseScraperAdapter):
    source_id = "csv"
    display_name = "CSV Import"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "allowed",
            "method": "manual_csv_import",
            "description": "Manuel CSV export — tüm platformlar için evrensel içe aktarma.",
            "requires_api_key": False,
            "recommended": True,
            "supported_platforms": ["Booking.com", "TripAdvisor", "Agoda", "Expedia", "Hotels.com", "Custom"],
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        csv_path = options.get("csv_path", "")
        limit = int(options.get("limit", 50))
        column_mapping: dict[str, str] = options.get("column_mapping") or {}
        default_platform = options.get("platform", "CSV Import")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")

        if not csv_path or not os.path.isfile(csv_path):
            return AdapterResult(
                error=f"CSV bulunamadı: {csv_path}",
                method="csv_import_failed",
            )

        reviews = []
        try:
            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return AdapterResult(error="CSV başlık satırı okunamadı", method="csv_import_failed")

                field_map = _build_field_map(reader.fieldnames, column_mapping)

                for row in reader:
                    comment = _get_field(row, field_map, "comment")
                    if not comment or len(comment.strip()) < 3:
                        continue

                    rating_raw = _get_field(row, field_map, "rating")
                    platform = _get_field(row, field_map, "platform") or default_platform
                    helpful_raw = _get_field(row, field_map, "helpful_count")
                    most_helpful_raw = _get_field(row, field_map, "is_most_helpful")

                    review = self._make_review(
                        comment=comment.strip(),
                        hotel=_get_field(row, field_map, "hotel") or hotel,
                        city=_get_field(row, field_map, "city") or city,
                        country=_get_field(row, field_map, "country") or country,
                        platform=platform,
                        rating=normalize_rating(rating_raw),
                        guest_name=_get_field(row, field_map, "guest_name") or "Anonim",
                        title=_get_field(row, field_map, "title"),
                        date=(_get_field(row, field_map, "date") or today_iso())[:10],
                        language=_get_field(row, field_map, "language"),
                        traveler_type=_get_field(row, field_map, "traveler_type"),
                        room_type=_get_field(row, field_map, "room_type"),
                        stay_duration=_get_field(row, field_map, "stay_duration"),
                        trip_purpose=_get_field(row, field_map, "trip_purpose"),
                        positive_text=_get_field(row, field_map, "positive_text"),
                        negative_text=_get_field(row, field_map, "negative_text"),
                        helpful_count=int(helpful_raw) if helpful_raw.isdigit() else 0,
                        is_most_helpful=most_helpful_raw.lower() in ("1", "true", "yes", "evet"),
                        source_url=csv_path,
                        ingestion_method="csv_import",
                        legal_notice="Manuel CSV import — yasal",
                    )
                    reviews.append(review)
                    if len(reviews) >= limit:
                        break

            if not reviews:
                return AdapterResult(
                    error="CSV'de geçerli yorum satırı yok (comment sütunu gerekli)",
                    method="csv_import_failed",
                )

            return AdapterResult(
                reviews=reviews,
                method="csv_import",
                warning=f"CSV'den {len(reviews)} yorum içe aktarıldı: {os.path.basename(csv_path)}",
            )
        except OSError as e:
            return AdapterResult(error=str(e), method="csv_import_failed")


def _build_field_map(headers: list[str], custom_mapping: dict[str, str]) -> dict[str, str]:
    """CSV başlıklarını standart alanlara eşle."""
    header_lower = {h.lower().strip(): h for h in headers}
    field_map: dict[str, str] = {}

    for std_field, aliases in COLUMN_ALIASES.items():
        if std_field in custom_mapping:
            mapped = custom_mapping[std_field]
            if mapped in headers:
                field_map[std_field] = mapped
            elif mapped.lower() in header_lower:
                field_map[std_field] = header_lower[mapped.lower()]
            continue
        for alias in aliases:
            if alias in headers:
                field_map[std_field] = alias
                break
            if alias.lower() in header_lower:
                field_map[std_field] = header_lower[alias.lower()]
                break

    return field_map


def _get_field(row: dict, field_map: dict[str, str], std_field: str) -> str:
    col = field_map.get(std_field)
    if not col:
        return ""
    return (row.get(col) or "").strip()
