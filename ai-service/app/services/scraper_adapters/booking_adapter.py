"""Booking.com adaptörü — ToS kısıtlı; CSV import şablonu ve parser."""
from __future__ import annotations

import os
from typing import Any

from app.services.review_ingestion_schema import normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter

TOS_WARNING = (
    "⚠ Booking.com otomatik kazımayı Hizmet Şartları'nda açıkça yasaklar. "
    "Booking Connectivity / Partner API yalnızca kayıtlı oteller içindir. "
    "Önerilen yöntem: Booking.com extranet veya yönetim panelinden CSV export → csv_import_adapter."
)

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "simulation",
    "datasets",
    "booking_import_template.csv",
)


class BookingAdapter(BaseScraperAdapter):
    source_id = "booking"
    display_name = "Booking.com"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "blocked",
            "method": "csv_import_only",
            "description": TOS_WARNING,
            "requires_api_key": False,
            "template_path": _TEMPLATE_PATH,
            "recommended": False,
            "fallback": "CSV import (booking_import_template.csv)",
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        csv_path = options.get("csv_path") or options.get("urls", {}).get("booking")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")

        if csv_path and os.path.isfile(csv_path):
            csv_opts = {
                **options,
                "csv_path": csv_path,
                "platform": "Booking.com",
                "column_mapping": options.get("column_mapping") or _booking_default_mapping(),
            }
            result = CsvImportAdapter().fetch_reviews(hotel_query, csv_opts)
            for r in result.reviews:
                r.platform = "Booking.com"
                r.hotel = r.hotel or hotel
                r.city = r.city or city
                r.country = r.country or country
                r.legal_notice = TOS_WARNING
            result.legal_notice = TOS_WARNING
            result.warning = (result.warning or "") + " " + TOS_WARNING
            return result

        # Demo sample CSV fallback
        sample = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
            "simulation", "sample_reviews", "booking_sample.csv",
        )
        if options.get("allow_fallback", True) and os.path.isfile(sample):
            csv_opts = {**options, "csv_path": sample, "platform": "Booking.com"}
            result = CsvImportAdapter().fetch_reviews(hotel_query, csv_opts)
            for r in result.reviews:
                r.platform = "Booking.com"
                r.hotel = r.hotel or hotel
                r.legal_notice = TOS_WARNING
            result.method = "booking_demo_csv"
            result.warning = TOS_WARNING + " Canlı kazıma desteklenmiyor. Demo CSV yüklendi."
            result.legal_notice = TOS_WARNING
            return result

        return AdapterResult(
            error="Booking.com doğrudan kazıma desteklenmiyor. CSV dosyası sağlayın.",
            method="booking_csv_required",
            warning=TOS_WARNING + f" Şablon: {_TEMPLATE_PATH}",
            legal_notice=TOS_WARNING,
        )


def _booking_default_mapping() -> dict[str, str]:
    return {
        "comment": "review_text",
        "rating": "score",
        "guest_name": "reviewer_name",
        "date": "review_date",
        "title": "review_title",
        "positive_text": "pros",
        "negative_text": "cons",
        "traveler_type": "traveler_type",
        "room_type": "room_type",
        "stay_duration": "nights",
        "trip_purpose": "trip_type",
        "language": "language",
    }
