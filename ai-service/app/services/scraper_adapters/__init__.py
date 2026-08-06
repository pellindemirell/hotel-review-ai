"""Çok platformlu yorum kazıma adaptörleri."""
from app.services.scraper_adapters.base import BaseScraperAdapter, AdapterResult
from app.services.scraper_adapters.google_places_adapter import GooglePlacesAdapter
from app.services.scraper_adapters.tripadvisor_adapter import TripAdvisorAdapter
from app.services.scraper_adapters.booking_adapter import BookingAdapter
from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter
from app.services.scraper_adapters.academic_dataset_adapter import AcademicDatasetAdapter
from app.services.scraper_adapters.agoda_adapter import AgodaScraper
from app.services.scraper_adapters.expedia_adapter import ExpediaScraper
from app.services.scraper_adapters.google_maps_playwright_adapter import GoogleMapsPlaywrightAdapter

ADAPTER_REGISTRY: dict[str, type[BaseScraperAdapter]] = {
    "google": GooglePlacesAdapter,
    "google_places": GooglePlacesAdapter,
    "tripadvisor": TripAdvisorAdapter,
    "booking": BookingAdapter,
    "csv": CsvImportAdapter,
    "academic": AcademicDatasetAdapter,
    "agoda": AgodaScraper,
    "expedia": ExpediaScraper,
    "google_maps_playwright": GoogleMapsPlaywrightAdapter,
    "playwright": GoogleMapsPlaywrightAdapter,
}


def get_adapter(source_id: str) -> BaseScraperAdapter:
    cls = ADAPTER_REGISTRY.get(source_id.lower())
    if not cls:
        raise ValueError(f"Bilinmeyen kaynak: {source_id}")
    return cls()


_unique_ids = ("google", "tripadvisor", "booking", "agoda", "expedia", "csv", "academic", "google_maps_playwright")


def list_adapters() -> list[dict]:
    return [get_adapter(k).legal_info() for k in _unique_ids]
