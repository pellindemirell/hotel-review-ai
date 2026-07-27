"""
Çok kaynaklı otel yorum kazıma orkestratörü.

Paralel adaptör çalıştırma, dedup, dil tespiti ve analiz pipeline entegrasyonu.
"""
from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from app.services.review_ingestion_schema import IngestedReview
from app.services.scraper_adapters import get_adapter, list_adapters
from app.services.scraper_adapters.base import AdapterResult
from app.services.translation_service import TranslationService

logger = logging.getLogger("ai_service")

# Kaynak ID → adaptör eşlemesi (csv platform-specific)
SOURCE_ALIASES = {
    "google": "google",
    "google_places": "google",
    "tripadvisor": "tripadvisor",
    "ta": "tripadvisor",
    "booking": "booking",
    "csv": "csv",
    "academic": "academic",
    "agoda": "agoda",
    "expedia": "expedia",
    "hotels.com": "expedia",
    "hotels_com": "expedia",
}


class MultiScraperService:
    """Birden fazla platformdan paralel yorum toplama."""

    @classmethod
    def scrape_hotel(
        cls,
        name: str,
        city: str = "",
        country: str = "",
        sources: Optional[list[str]] = None,
        urls: Optional[dict[str, str]] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Çoklu kaynaktan yorum çek, birleştir, dedup et.

        Args:
            name: Otel adı
            city: Şehir
            country: Ülke
            sources: ["google", "csv", "tripadvisor", "booking", "academic"]
            urls: {"google": "...", "tripadvisor": "...", "booking": "csv_path"}
            options: limit, api_key, csv_path, column_mapping, analyze, allow_fallback
        """
        opts = dict(options or {})
        opts.setdefault("limit", 10)
        opts["hotel_name"] = name
        opts["city"] = city
        opts["country"] = country
        opts["urls"] = urls or {}

        source_list = sources or ["google"]
        normalized_sources = [_normalize_source(s) for s in source_list]

        # Paralel fetch
        results: list[tuple[str, AdapterResult]] = []
        with ThreadPoolExecutor(max_workers=min(len(normalized_sources), 4)) as pool:
            futures = {
                pool.submit(cls._fetch_source, src, name, opts): src
                for src in normalized_sources
            }
            for fut in as_completed(futures):
                src = futures[fut]
                try:
                    results.append((src, fut.result()))
                except Exception as e:
                    logger.error(f"Adaptör hatası ({src}): {e}")
                    results.append((src, AdapterResult(error=str(e), method=f"{src}_error")))

        # Birleştir ve dedup
        all_reviews: list[IngestedReview] = []
        warnings: list[str] = []
        errors: list[str] = []
        methods: list[str] = []
        legal_notices: list[str] = []

        for src, result in results:
            if result.warning:
                warnings.append(f"[{src}] {result.warning}")
            if result.error and not result.reviews:
                errors.append(f"[{src}] {result.error}")
            if result.method:
                methods.append(result.method)
            if result.legal_notice:
                legal_notices.append(result.legal_notice)
            all_reviews.extend(result.reviews)

        deduped = cls.deduplicate_reviews(all_reviews)

        # Dil tespiti + çeviri (analiz öncesi metadata)
        for review in deduped:
            cls.enrich_language(review)

        # Kaynak bazlı istatistikler
        source_stats: dict[str, int] = {}
        for src in normalized_sources:
            count = sum(
                1 for r in deduped
                if _review_matches_source(r, src)
            )
            source_stats[src] = count

        # Analiz pipeline
        analyze = opts.get("analyze", True)
        api_key = opts.get("api_key")
        store = opts.get("store", True)

        if analyze:
            for review in deduped:
                try:
                    review.to_analysis_pipeline(api_key=api_key, store=store)
                except Exception as e:
                    logger.warning(f"Pipeline hatası: {e}")

        return {
            "reviews": [r.to_dict() for r in deduped],
            "total": len(deduped),
            "raw_total": len(all_reviews),
            "duplicates_removed": len(all_reviews) - len(deduped),
            "sources_requested": normalized_sources,
            "sources_succeeded": [src for src, r in results if r.reviews],
            "source_stats": source_stats,
            "methods": methods,
            "warnings": warnings,
            "errors": errors,
            "legal_notices": list(set(legal_notices)),
            "hotel": name,
            "city": city,
            "country": country,
        }

    @classmethod
    def _fetch_source(cls, source_id: str, hotel_query: str, options: dict) -> AdapterResult:
        adapter = get_adapter(source_id)

        # Platform-specific URL/CSV path
        urls = options.get("urls", {})
        if source_id == "csv" and options.get("csv_path"):
            pass
        elif source_id in urls:
            val = urls[source_id]
            if source_id == "google":
                if val.startswith("ChIJ") or "place_id" in val:
                    options = {**options, "place_id": val}
                else:
                    options = {**options, "url": val}
            elif source_id in ("booking",) and os.path.isfile(val):
                options = {**options, "csv_path": val}
            elif source_id in ("agoda", "expedia", "tripadvisor", "booking"):
                options = {**options, "url": val, "urls": {**urls, source_id: val}}
            elif source_id == "csv":
                options = {**options, "csv_path": val}

        return adapter.fetch_reviews(hotel_query, options)

    @classmethod
    def deduplicate_reviews(cls, reviews: list[IngestedReview]) -> list[IngestedReview]:
        """Yorum hash'ine göre dedup."""
        seen: set[str] = set()
        out: list[IngestedReview] = []
        for r in reviews:
            h = r.ensure_hash().comment_hash
            if h in seen:
                continue
            seen.add(h)
            out.append(r)
        return out

    @classmethod
    def enrich_language(cls, review: IngestedReview) -> IngestedReview:
        """Dil tespiti ve Türkçe çeviri metadata'sı."""
        if not review.comment:
            return review
        if not review.language:
            try:
                from langdetect import detect
                review.language = detect(review.comment)
            except Exception:
                logger.warning("Language detection failed, using heuristic", exc_info=True)
                review.language = cls._heuristic_language(review.comment)

        turkish, detected = TranslationService.translate_to_turkish(
            review.comment, source_lang=review.language
        )
        if not review.analysis.translated_comment:
            review.analysis.translated_comment = turkish
            review.analysis.detected_language = detected
        return review

    @staticmethod
    def _heuristic_language(text: str) -> str:
        import re
        if re.search(r"[ğüşıöçĞÜŞİÖÇ]", text):
            return "tr"
        if re.search(r"[а-яА-Я]", text):
            return "ru"
        if re.search(r"[äöüßÄÖÜ]", text):
            return "de"
        return "en"

    @classmethod
    def list_sources(cls) -> list[dict]:
        """Tüm adaptörlerin yasal durum bilgisi."""
        seen = set()
        out = []
        for info in list_adapters():
            if info["id"] not in seen:
                seen.add(info["id"])
                out.append(info)
        return out

    @classmethod
    def comment_hash(cls, comment: str) -> str:
        normalized = (comment or "").strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _normalize_source(source: str) -> str:
    s = source.strip().lower()
    return SOURCE_ALIASES.get(s, s)


def _review_matches_source(review, source_id: str) -> bool:
    """Yorumun hangi kaynağa ait olduğunu platform/ingestion_method ile eşle."""
    from app.services.review_source_schema import Platform

    plat = Platform.from_string(review.platform or "").value
    method = (review.ingestion_method or "").lower()
    src = source_id.lower()
    if plat == src:
        return True
    if src in method or src in (review.platform or "").lower():
        return True
    aliases = {
        "google": ("google", "places"),
        "tripadvisor": ("tripadvisor", "ta"),
        "booking": ("booking",),
        "agoda": ("agoda",),
        "expedia": ("expedia",),
    }
    for alias in aliases.get(src, (src,)):
        if alias in method or alias in (review.platform or "").lower():
            return True
    return False
