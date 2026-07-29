"""Google Places API adaptörü — birincil yasal kaynak."""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import unquote

from app.services.review_ingestion_schema import IngestedReview, normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_service import ScraperService


class GooglePlacesAdapter(BaseScraperAdapter):
    source_id = "google"
    display_name = "Google Places API"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "allowed",
            "method": "official_api",
            "description": "Google Places API (Place Details) — resmi, yasal yöntem.",
            "requires_api_key": True,
            "env_var": "GOOGLE_PLACES_API_KEY",
            "limitations": "Google en fazla ~5 yorum döndürür. Tam arşiv için CSV import kullanın.",
            "recommended": True,
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        limit = int(options.get("limit", 10))
        api_key = options.get("google_places_api_key") or options.get("api_key") or os.getenv("GOOGLE_PLACES_API_KEY")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")
        place_id = options.get("place_id") or options.get("urls", {}).get("google")
        url = options.get("url", "")

        if not api_key:
            return AdapterResult(
                error="GOOGLE_PLACES_API_KEY tanımlı değil.",
                method="google_places_api",
                legal_notice=self.legal_info()["description"],
            )

        # place_id çözümle
        if not place_id and url:
            place_id = ScraperService.extract_google_place_id(url)
        if not place_id and hotel_query:
            query = hotel_query
            if city:
                query = f"{hotel_query} {city}"
            if country:
                query = f"{query} {country}"
            place_id, err = ScraperService.fetch_place_id_from_query(query, api_key)
            if err and not place_id:
                return AdapterResult(
                    error=f"Place ID bulunamadı: {err}",
                    method="google_places_api",
                    legal_notice=self.legal_info()["description"],
                )

        if not place_id:
            return AdapterResult(
                error="place_id veya otel adı gerekli.",
                method="google_places_api",
            )

        raw_reviews, err = ScraperService.scrape_google_places_combined(place_id, limit, api_key)
        if not raw_reviews:
            return AdapterResult(
                error=err or "Google Places API yorum döndürmedi.",
                method="google_places_api",
                legal_notice=self.legal_info()["description"],
            )

        reviews = []
        for raw in raw_reviews:
            lang = _detect_language_simple(raw.get("comment", ""))
            reviews.append(
                self._make_review(
                    comment=raw.get("comment", ""),
                    hotel=hotel,
                    city=city,
                    country=country,
                    platform="Google",
                    rating=normalize_rating(raw.get("rating")),
                    guest_name=raw.get("guest_name", "Anonim"),
                    date=raw.get("review_date") or today_iso(),
                    language=lang,
                    source_url=url or f"place_id:{place_id}",
                    ingestion_method="google_places_api",
                    legal_notice="Resmi Google Places API",
                )
            )

        return AdapterResult(
            reviews=reviews,
            method="google_places_api",
            warning=(
                f"Google Places API ile {len(reviews)} gerçek yorum çekildi. "
                "(Google en fazla ~5 yorum döndürür — tam arşiv için CSV import kullanın.)"
            ),
            legal_notice=self.legal_info()["description"],
        )


def _detect_language_simple(text: str) -> str:
    if not text:
        return ""
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        # Basit heuristic
        if re.search(r"[ğüşıöçĞÜŞİÖÇ]", text):
            return "tr"
        if re.search(r"[а-яА-Я]", text):
            return "ru"
        if re.search(r"[äöüßÄÖÜ]", text):
            return "de"
        return "en"
