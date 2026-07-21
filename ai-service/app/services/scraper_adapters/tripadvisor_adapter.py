"""TripAdvisor adaptörü — API/URL dene, başarısızsa demo + uyarı."""
from __future__ import annotations

from typing import Any

from app.services.review_ingestion_schema import normalize_rating, today_iso
from app.services.scraper_adapters.base import AdapterResult, BaseScraperAdapter
from app.services.scraper_service import ScraperService, FALLBACK_REVIEWS


TOS_WARNING = (
    "⚠ TripAdvisor otomatik HTML kazıması Hizmet Şartları'nı ihlal edebilir ve 403 bot "
    "koruması nedeniyle genelde başarısız olur. Önerilen yöntem: TripAdvisor'dan manuel "
    "CSV export veya csv_import_adapter kullanın."
)


class TripAdvisorAdapter(BaseScraperAdapter):
    source_id = "tripadvisor"
    display_name = "TripAdvisor"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "restricted",
            "method": "html_scraping_blocked",
            "description": TOS_WARNING,
            "requires_api_key": False,
            "limitations": "Resmi public review API yok. Content API partner programı gerekir.",
            "recommended": False,
            "fallback": "CSV import (tripadvisor_import_template.csv)",
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        limit = int(options.get("limit", 10))
        url = options.get("urls", {}).get("tripadvisor") or options.get("url", "")
        hotel = options.get("hotel_name", hotel_query)
        city = options.get("city", "")
        country = options.get("country", "")
        allow_demo = options.get("allow_fallback", True)

        reviews = []
        method = "tripadvisor_blocked"
        warning = TOS_WARNING

        if url and "tripadvisor" in url.lower():
            raw = ScraperService.scrape_tripadvisor_reviews(url, limit)
            if raw:
                method = "tripadvisor_html"
                warning = TOS_WARNING + " (HTML kazıma başarılı — yine de ToS riski var.)"
                for r in raw:
                    reviews.append(
                        self._make_review(
                            comment=r.get("comment", ""),
                            hotel=hotel,
                            city=city,
                            country=country,
                            platform="TripAdvisor",
                            rating=normalize_rating(r.get("rating")),
                            guest_name=r.get("guest_name", "Anonim"),
                            date=r.get("review_date") or today_iso(),
                            source_url=url,
                            ingestion_method=method,
                            legal_notice=TOS_WARNING,
                        )
                    )
                return AdapterResult(
                    reviews=reviews[:limit],
                    method=method,
                    warning=warning,
                    legal_notice=TOS_WARNING,
                )

        # Demo fallback — TripAdvisor kaynaklı örnekler
        if allow_demo:
            ta_items = [r for r in FALLBACK_REVIEWS if "TripAdvisor" in r.get("source", "")]
            if not ta_items:
                ta_items = FALLBACK_REVIEWS[:limit]
            for item in ta_items[:limit]:
                reviews.append(
                    self._make_review(
                        comment=item["comment"],
                        hotel=hotel or "Demo Hotel",
                        city=city,
                        country=country,
                        platform="TripAdvisor (Demo)",
                        rating=normalize_rating(item.get("rating")),
                        guest_name=item.get("guest_name", "Anonim"),
                        date=today_iso(),
                        ingestion_method="tripadvisor_demo",
                        legal_notice=TOS_WARNING,
                    )
                )
            return AdapterResult(
                reviews=reviews,
                method="tripadvisor_demo",
                warning=(
                    TOS_WARNING
                    + " Canlı kazıma başarısız (403). Demo yorumlar yüklendi — "
                    "gerçek veri için CSV import kullanın."
                ),
                legal_notice=TOS_WARNING,
            )

        return AdapterResult(
            error="TripAdvisor URL gerekli veya allow_fallback=true.",
            method="tripadvisor_blocked",
            warning=TOS_WARNING,
            legal_notice=TOS_WARNING,
        )
