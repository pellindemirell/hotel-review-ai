"""
Standart çok platformlu otel yorum kaydı şeması.

Tüm kazıma adaptörleri bu şemaya dönüştürür; analiz pipeline'ı IngestedReview ile entegre olur.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class Platform(str, Enum):
    GOOGLE = "google"
    BOOKING = "booking"
    TRIPADVISOR = "tripadvisor"
    AGODA = "agoda"
    EXPEDIA = "expedia"
    HOTELS_COM = "hotels_com"
    ETSTUR = "etstur"
    TATILBUDUR = "tatilbudur"
    ODAMAX = "odamax"
    OTELZ = "otelz"
    AIRBNB = "airbnb"
    HOSTELWORLD = "hostelworld"
    YELP = "yelp"
    HOLIDAYCHECK = "holidaycheck"
    CSV_IMPORT = "csv_import"
    DEMO = "demo"

    @classmethod
    def from_string(cls, value: str) -> "Platform":
        v = (value or "").strip().lower().replace(".com", "").replace(" ", "_")
        aliases = {
            "google_places": cls.GOOGLE,
            "google_places_api": cls.GOOGLE,
            "google_maps": cls.GOOGLE,
            "google": cls.GOOGLE,
            "ta": cls.TRIPADVISOR,
            "tripadvisor_(demo)": cls.TRIPADVISOR,
            "hotels.com": cls.HOTELS_COM,
            "hotels": cls.HOTELS_COM,
            "csv": cls.CSV_IMPORT,
            "csv_import": cls.CSV_IMPORT,
        }
        if v in aliases:
            return aliases[v]
        # Substring eşleme
        for key, plat in [
            ("google", cls.GOOGLE), ("booking", cls.BOOKING),
            ("tripadvisor", cls.TRIPADVISOR), ("agoda", cls.AGODA),
            ("expedia", cls.EXPEDIA), ("airbnb", cls.AIRBNB),
        ]:
            if key in v:
                return plat
        try:
            return cls(v)
        except ValueError:
            return cls.DEMO


# Platform badge renkleri (UI)
PLATFORM_BADGE_COLORS: dict[str, str] = {
    Platform.GOOGLE.value: "#4285F4",
    Platform.BOOKING.value: "#003580",
    Platform.TRIPADVISOR.value: "#00AF87",
    Platform.AGODA.value: "#5392F9",
    Platform.EXPEDIA.value: "#FFCC00",
    Platform.HOTELS_COM.value: "#D32F2F",
    Platform.ETSTUR.value: "#E30613",
    Platform.TATILBUDUR.value: "#FF6600",
    Platform.ODAMAX.value: "#0066CC",
    Platform.OTELZ.value: "#7B2D8E",
    Platform.AIRBNB.value: "#FF5A5F",
    Platform.HOSTELWORLD.value: "#F25621",
    Platform.YELP.value: "#D32323",
    Platform.HOLIDAYCHECK.value: "#005EB8",
    Platform.CSV_IMPORT.value: "#6B7280",
    Platform.DEMO.value: "#9CA3AF",
}


PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    Platform.GOOGLE.value: "Google",
    Platform.BOOKING.value: "Booking.com",
    Platform.TRIPADVISOR.value: "TripAdvisor",
    Platform.AGODA.value: "Agoda",
    Platform.EXPEDIA.value: "Expedia",
    Platform.HOTELS_COM.value: "Hotels.com",
    Platform.ETSTUR.value: "Etstur",
    Platform.TATILBUDUR.value: "Tatilbudur",
    Platform.ODAMAX.value: "Odamax",
    Platform.OTELZ.value: "Otelz",
    Platform.AIRBNB.value: "Airbnb",
    Platform.HOSTELWORLD.value: "Hostelworld",
    Platform.YELP.value: "Yelp",
    Platform.HOLIDAYCHECK.value: "HolidayCheck",
    Platform.CSV_IMPORT.value: "CSV Import",
    Platform.DEMO.value: "Demo",
}


@dataclass
class ScrapedReview:
    """Zengin yorum kaydı — tüm platformlardan birleşik standart."""
    hotel_name: str = ""
    country: str = ""
    city: str = ""
    language: str = ""
    platform: str = ""
    platform_url: str = ""
    review_id: str = ""
    date: str = ""
    rating: float = 0.0
    title: str = ""
    comment: str = ""
    traveler_type: str = ""
    room_type: str = ""
    stay_duration: str = ""
    trip_purpose: str = ""
    positive_text: str = ""
    negative_text: str = ""
    helpful_count: int = 0
    is_most_helpful: bool = False
    guest_name: str = "Anonim"
    source_detected: str = ""
    scrape_method: str = ""
    comment_hash: str = field(default="", repr=False)

    def __post_init__(self):
        if not self.comment_hash and self.comment:
            self.comment_hash = self.compute_hash()

    def compute_hash(self) -> str:
        normalized = (self.comment or "").strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @property
    def platform_enum(self) -> Platform:
        return Platform.from_string(self.platform)

    @property
    def badge_color(self) -> str:
        key = self.platform_enum.value
        return PLATFORM_BADGE_COLORS.get(key, "#6B7280")

    @property
    def badge_label(self) -> str:
        key = self.platform_enum.value
        return PLATFORM_DISPLAY_NAMES.get(key, self.platform or "Unknown")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["badge_color"] = self.badge_color
        d["badge_label"] = self.badge_label
        d["platform_id"] = self.platform_enum.value
        return d

    def to_ingested_review(self):
        """IngestedReview (Pydantic) modeline dönüştür."""
        from app.services.review_ingestion_schema import IngestedReview

        return IngestedReview(
            hotel=self.hotel_name,
            country=self.country,
            city=self.city,
            language=self.language,
            platform=self.badge_label,
            date=self.date,
            rating=self.rating,
            title=self.title,
            comment=self.comment,
            traveler_type=self.traveler_type,
            room_type=self.room_type,
            stay_duration=self.stay_duration,
            trip_purpose=self.trip_purpose,
            positive_text=self.positive_text,
            negative_text=self.negative_text,
            guest_name=self.guest_name,
            comment_hash=self.comment_hash or self.compute_hash(),
            source_url=self.platform_url,
            ingestion_method=self.scrape_method or self.source_detected,
            helpful_count=self.helpful_count,
            is_most_helpful=self.is_most_helpful,
            review_id=self.review_id,
        )

    @classmethod
    def from_legacy_dict(cls, raw: dict, hotel_name: str = "", platform: str = "") -> "ScrapedReview":
        """Eski ScraperService dict formatından dönüştür."""
        src = raw.get("source") or platform or ""
        plat = Platform.from_string(src).value
        return cls(
            hotel_name=hotel_name or raw.get("hotel", ""),
            country=raw.get("country", ""),
            city=raw.get("city", ""),
            language=raw.get("language", ""),
            platform=plat,
            platform_url=raw.get("platform_url") or raw.get("source_url", ""),
            review_id=raw.get("review_id", ""),
            date=raw.get("review_date") or raw.get("date", ""),
            rating=float(raw.get("rating") or 0),
            title=raw.get("title", ""),
            comment=raw.get("comment", ""),
            traveler_type=raw.get("traveler_type", ""),
            room_type=raw.get("room_type", ""),
            stay_duration=raw.get("stay_duration", ""),
            trip_purpose=raw.get("trip_purpose", ""),
            positive_text=raw.get("positive_text", ""),
            negative_text=raw.get("negative_text", ""),
            helpful_count=int(raw.get("helpful_count") or 0),
            is_most_helpful=bool(raw.get("is_most_helpful")),
            guest_name=raw.get("guest_name", "Anonim"),
            source_detected=raw.get("source_detected") or plat,
            scrape_method=raw.get("scrape_method") or raw.get("method", ""),
        )
