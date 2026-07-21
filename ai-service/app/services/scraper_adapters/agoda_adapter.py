"""Agoda adaptörü — ToS kısıtlı; CSV import veya demo fallback."""
from __future__ import annotations

import os
from typing import Any

from app.services.review_ingestion_schema import normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter

TOS_WARNING = (
    "⚠ Agoda otomatik kazımayı Hizmet Şartları'nda kısıtlar. "
    "Resmi Agoda Partner API yalnızca kayıtlı oteller içindir. "
    "Önerilen yöntem: Agoda extranet veya manuel CSV export."
)

_SAMPLE_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "simulation",
    "sample_reviews",
    "agoda_sample.csv",
)


class AgodaScraper(BaseScraperAdapter):
    source_id = "agoda"
    display_name = "Agoda"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "blocked",
            "method": "csv_import_or_demo",
            "description": TOS_WARNING,
            "requires_api_key": False,
            "recommended": False,
            "fallback": "simulation/sample_reviews/agoda_sample.csv",
        }

    def fetch_reviews(self, hotel_query: str, options: dict[str, Any]) -> AdapterResult:
        csv_path = options.get("csv_path") or options.get("urls", {}).get("agoda")
        url = options.get("url") or options.get("urls", {}).get("agoda", "")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")
        limit = int(options.get("limit", 10))
        allow_demo = options.get("allow_fallback", True)

        # CSV path (URL yerine dosya yolu olabilir)
        if csv_path and os.path.isfile(csv_path):
            return self._import_csv(csv_path, hotel, city, country, options)

        # URL verilmiş ama canlı kazıma desteklenmiyor
        if url and url.startswith("http"):
            if allow_demo and os.path.isfile(_SAMPLE_CSV):
                result = self._import_csv(_SAMPLE_CSV, hotel, city, country, options)
                result.warning = (
                    TOS_WARNING
                    + " Canlı Agoda kazıması desteklenmiyor. Demo CSV yüklendi."
                )
                result.method = "agoda_demo_csv"
                return result
            return AdapterResult(
                error="Agoda doğrudan kazıma desteklenmiyor.",
                method="agoda_blocked",
                warning=TOS_WARNING + " CSV dosyası veya sample_reviews/agoda_sample.csv kullanın.",
                legal_notice=TOS_WARNING,
            )

        if allow_demo and os.path.isfile(_SAMPLE_CSV):
            result = self._import_csv(_SAMPLE_CSV, hotel, city, country, options)
            result.method = "agoda_demo_csv"
            result.warning = TOS_WARNING + " Demo örnek veri yüklendi."
            return result

        return AdapterResult(
            error="Agoda URL veya CSV gerekli.",
            method="agoda_blocked",
            warning=TOS_WARNING,
            legal_notice=TOS_WARNING,
        )

    def _import_csv(self, csv_path: str, hotel: str, city: str, country: str, options: dict) -> AdapterResult:
        csv_opts = {**options, "csv_path": csv_path, "platform": "Agoda"}
        result = CsvImportAdapter().fetch_reviews(hotel, csv_opts)
        for r in result.reviews:
            r.platform = "Agoda"
            r.hotel = r.hotel or hotel
            r.city = r.city or city
            r.country = r.country or country
            r.legal_notice = TOS_WARNING
        result.legal_notice = TOS_WARNING
        return result
