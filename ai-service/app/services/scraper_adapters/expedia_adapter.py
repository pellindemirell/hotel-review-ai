"""Expedia adaptörü — ToS kısıtlı; CSV import veya demo fallback."""
from __future__ import annotations

import os
from typing import Any

from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter

TOS_WARNING = (
    "⚠ Expedia otomatik kazımayı Hizmet Şartları'nda kısıtlar. "
    "Expedia Partner Central API yalnızca kayıtlı oteller içindir. "
    "Önerilen yöntem: Expedia extranet veya manuel CSV export."
)

_SAMPLE_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "simulation",
    "sample_reviews",
    "expedia_sample.csv",
)


class ExpediaScraper(BaseScraperAdapter):
    source_id = "expedia"
    display_name = "Expedia"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "blocked",
            "method": "csv_import_or_demo",
            "description": TOS_WARNING,
            "requires_api_key": False,
            "recommended": False,
            "fallback": "simulation/sample_reviews/expedia_sample.csv",
        }

    def fetch_reviews(self, hotel_query: str, options: dict[str, Any]) -> AdapterResult:
        csv_path = options.get("csv_path") or options.get("urls", {}).get("expedia")
        url = options.get("url") or options.get("urls", {}).get("expedia", "")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")
        allow_demo = options.get("allow_fallback", True)

        if csv_path and os.path.isfile(csv_path):
            return self._import_csv(csv_path, hotel, city, country, options)

        if url and url.startswith("http"):
            if allow_demo and os.path.isfile(_SAMPLE_CSV):
                result = self._import_csv(_SAMPLE_CSV, hotel, city, country, options)
                result.warning = (
                    TOS_WARNING
                    + " Canlı Expedia kazıması desteklenmiyor. Demo CSV yüklendi."
                )
                result.method = "expedia_demo_csv"
                return result
            return AdapterResult(
                error="Expedia doğrudan kazıma desteklenmiyor.",
                method="expedia_blocked",
                warning=TOS_WARNING,
                legal_notice=TOS_WARNING,
            )

        if allow_demo and os.path.isfile(_SAMPLE_CSV):
            result = self._import_csv(_SAMPLE_CSV, hotel, city, country, options)
            result.method = "expedia_demo_csv"
            result.warning = TOS_WARNING + " Demo örnek veri yüklendi."
            return result

        return AdapterResult(
            error="Expedia URL veya CSV gerekli.",
            method="expedia_blocked",
            warning=TOS_WARNING,
            legal_notice=TOS_WARNING,
        )

    def _import_csv(self, csv_path: str, hotel: str, city: str, country: str, options: dict) -> AdapterResult:
        csv_opts = {**options, "csv_path": csv_path, "platform": "Expedia"}
        result = CsvImportAdapter().fetch_reviews(hotel, csv_opts)
        for r in result.reviews:
            r.platform = "Expedia"
            r.hotel = r.hotel or hotel
            r.city = r.city or city
            r.country = r.country or country
            r.legal_notice = TOS_WARNING
        result.legal_notice = TOS_WARNING
        return result
