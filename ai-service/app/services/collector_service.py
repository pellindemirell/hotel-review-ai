"""Review collector API köprüsü — simulation/review_collector paketini ai-service'e bağlar."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SIM_DIR = os.path.join(_PROJECT_ROOT, "simulation")
if _SIM_DIR not in sys.path:
    sys.path.insert(0, _SIM_DIR)

try:
    from review_collector.paste_importer import PasteImporter  # type: ignore
    from review_collector.paste_bulk_parser import PasteBulkParser, is_google_bulk_format  # type: ignore
    from review_collector.exporters.csv_export import CsvExporter  # type: ignore
    from review_collector.schema import CSV_COLUMNS  # type: ignore
except ImportError:
    class PasteImporter:
        def __init__(self, **kwargs): pass
        def parse_blocks(self, text): return []

    class PasteBulkParser:
        def __init__(self, **kwargs): pass
        def parse(self, text): return []

    def is_google_bulk_format(text): return False
    CSV_COLUMNS = []


def _parse_paste_text(
    text: str,
    hotel_name: str = "",
    country: str = "TR",
    city: str = "Belek",
    platform: str = "manual",
    url: str = "",
):
    """Google bulk veya klasik yapıştır formatını otomatik seç."""
    if is_google_bulk_format(text):
        return PasteBulkParser(
            hotel_name=hotel_name,
            country=country,
            city=city,
            url=url,
            ref_date=datetime.now(),
        ).parse(text)
    return PasteImporter(
        hotel_name=hotel_name,
        country=country,
        city=city,
        platform=platform,
        url=url,
    ).parse_blocks(text)


def import_paste_text(
    text: str,
    hotel_name: str = "",
    country: str = "TR",
    city: str = "Belek",
    platform: str = "manual",
    output_path: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Yapıştırılmış metni parse edip CSV'ye yazar."""
    reviews = _parse_paste_text(text, hotel_name=hotel_name, country=country, city=city, platform=platform)
    if not reviews:
        return {"success": False, "error": "Geçerli yorum bloğu bulunamadı", "count": 0}

    if not output_path:
        data_dir = os.path.join(_SIM_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, "collected_reviews.csv")

    exporter = CsvExporter(output_path)
    result = exporter.write(reviews, force=force, append=not force)
    return {
        "success": True,
        "count": result["written"],
        "skipped_dup": result["skipped_dup"],
        "path": result["path"],
        "preview": [r.to_csv_row() for r in reviews[:5]],
        "format_detected": "google_bulk" if is_google_bulk_format(text) else "classic",
    }


def import_bulk_paste(
    text: str,
    hotel_name: str = "Crystal Waterworld Resort & Spa",
    country: str = "TR",
    city: str = "Belek",
    output_path: Optional[str] = None,
    force: bool = True,
    analyze: bool = True,
    limit: int = 50,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Google/TripAdvisor bulk yapıştır → CSV + opsiyonel analiz."""
    if not output_path:
        output_path = os.path.join(_SIM_DIR, "data", "crystal_google_reviews.csv")

    parse_result = import_paste_text(
        text=text,
        hotel_name=hotel_name,
        country=country,
        city=city,
        platform="google",
        output_path=output_path,
        force=force,
    )
    if not parse_result.get("success"):
        return parse_result

    analysis = None
    if analyze and parse_result.get("path"):
        analysis = analyze_collected_csv(
            csv_path=parse_result["path"],
            hotel_name=hotel_name,
            platform="google",
            limit=limit,
            analyze=True,
            api_key=api_key,
        )

    return {
        **parse_result,
        "analysis_total": (analysis or {}).get("total"),
        "analysis_reviews": (analysis or {}).get("reviews", []),
    }


def get_csv_template() -> str:
    return CsvExporter.empty_template()


def analyze_collected_csv(
    csv_path: str,
    hotel_name: str = "",
    platform: str = "manual",
    limit: int = 50,
    analyze: bool = True,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Toplanan CSV'yi MultiScraperService ile analiz et."""
    from app.services.multi_scraper_service import MultiScraperService
    return MultiScraperService.scrape_hotel(
        name=hotel_name or "Collected Reviews",
        sources=["csv"],
        options={
            "csv_path": csv_path,
            "limit": limit,
            "analyze": analyze,
            "api_key": api_key,
            "platform": platform,
            "hotel_name": hotel_name,
            "allow_fallback": False,
        },
    )
