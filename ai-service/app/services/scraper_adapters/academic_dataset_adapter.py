"""Akademik açık veri seti adaptörü — HotelRec tarzı CSV."""
from __future__ import annotations

import os
from typing import Any

from app.services.review_ingestion_schema import normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter

_DATASETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "simulation",
    "datasets",
)

_DEFAULT_SAMPLE = os.path.join(_DATASETS_DIR, "sample_multilang_reviews.csv")


class AcademicDatasetAdapter(BaseScraperAdapter):
    source_id = "academic"
    display_name = "Academic Dataset (HotelRec)"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "allowed",
            "method": "open_dataset",
            "description": (
                "Akademik açık veri setleri (HotelRec, TripAdvisor Hotel Review Dataset vb.) — "
                "araştırma amaçlı, yasal kullanım."
            ),
            "requires_api_key": False,
            "default_path": _DEFAULT_SAMPLE,
            "recommended": True,
            "references": [
                "HotelRec: https://github.com/HotelRec/HotelRec",
                "TripAdvisor Hotel Review Dataset (Kaggle)",
            ],
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        dataset_path = (
            options.get("csv_path")
            or options.get("dataset_path")
            or _DEFAULT_SAMPLE
        )
        hotel = options.get("hotel_name", hotel_query)

        if not os.path.isfile(dataset_path):
            return AdapterResult(
                error=f"Veri seti bulunamadı: {dataset_path}",
                method="academic_dataset_missing",
                warning="simulation/datasets/sample_multilang_reviews.csv oluşturun veya yol belirtin.",
            )

        csv_opts = {
            **options,
            "csv_path": dataset_path,
            "platform": options.get("platform", "Academic Dataset"),
            "column_mapping": options.get("column_mapping") or _academic_mapping(),
        }
        result = CsvImportAdapter().fetch_reviews(hotel, csv_opts)
        result.method = "academic_dataset"
        for r in result.reviews:
            r.ingestion_method = "academic_dataset"
            r.legal_notice = "Akademik açık veri seti — araştırma amaçlı"
            if hotel and not r.hotel:
                r.hotel = hotel
        result.legal_notice = self.legal_info()["description"]
        return result


def _academic_mapping() -> dict[str, str]:
    return {
        "comment": "review_text",
        "rating": "rating",
        "guest_name": "reviewer",
        "date": "review_date",
        "language": "language",
        "hotel": "hotel_name",
        "city": "city",
        "country": "country",
        "platform": "platform",
    }
