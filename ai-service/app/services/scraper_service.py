"""
Otel yorum kazıma servisi.

KAYNAK ÖNCELİĞİ:
  1. Google Places API (GOOGLE_PLACES_API_KEY env) — yasal, önerilen
  2. TripAdvisor HTML kazıma (rate limit + User-Agent rotasyonu)
  3. Google Maps HTML (sınırlı; çoğu zaman JS ile korunur)
  4. Yerel demo/fallback CSV (canlı kazıma başarısız olursa)

ToS UYARISI:
  TripAdvisor ve Google Maps otomatik kazımayı hizmet şartlarında kısıtlayabilir.
  Üretim ortamında Google Places API veya resmi partner entegrasyonu kullanın.
"""

import os
import re
import json
import time
import random
import logging
import csv
import hashlib
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from app.services.review_source_schema import (
    ScrapedReview,
    Platform,
    PLATFORM_BADGE_COLORS,
    PLATFORM_DISPLAY_NAMES,
)

logger = logging.getLogger("ai_service")

# Demo fallback — Crystal Waterworld gerçekçi çok dilli yorumlar
FALLBACK_REVIEWS = [
    {"guest_name": "Hans Müller", "comment": "Das Essen im Crystal Waterworld war leider immer kalt. Lange Schlange am Buffet.", "rating": 2, "source": "TripAdvisor"},
    {"guest_name": "Sarah Jenkins", "comment": "The pool area was incredibly dirty and there was too much chlorine in the water.", "rating": 3, "source": "TripAdvisor"},
    {"guest_name": "Ahmet Yılmaz", "comment": "Crystal Waterworld resepsiyonu çok yavaştı. Girişte bizi 2 saat beklettiler.", "rating": 1, "source": "Google"},
    {"guest_name": "Olga Petrova", "comment": "Кондиционер в номере 1205 вообще не работал, нам было очень жарко спать.", "rating": 1, "source": "Google"},
    {"guest_name": "Mehmet Kaya", "comment": "Oda temizliği berbattı, havlular lekeliydi. Asla tavsiye etmem.", "rating": 1, "source": "TripAdvisor"},
    {"guest_name": "Ayşe Demir", "comment": "Spa merkezindeki masaj harikaydı, çalışanlar çok profesyoneldi.", "rating": 5, "source": "Google"},
    {"guest_name": "John Davis", "comment": "Wi-Fi connection was extremely slow. Could not check emails.", "rating": 2, "source": "TripAdvisor"},
    {"guest_name": "Elif Şahin", "comment": "Yemek çeşitliliği çok güzeldi, tatlı büfesine bayıldık.", "rating": 5, "source": "Booking.com"},
    {"guest_name": "Katrin Schmidt", "comment": "Die Animation am Abend war sehr laut. Wir konnten bis Mitternacht nicht schlafen.", "rating": 2, "source": "TripAdvisor"},
    {"guest_name": "Michael Brown", "comment": "We were charged extra for drinks at breakfast. Very expensive, not worth the money.", "rating": 2, "source": "Google"},
    {"guest_name": "Dmitry Smirnov", "comment": "Пляж очень чистый, но лежаков на всех не хватает.", "rating": 3, "source": "TripAdvisor"},
    {"guest_name": "Wolfgang Becker", "comment": "Beim Check-out gab es Probleme mit der Abrechnung.", "rating": 1, "source": "TripAdvisor"},
]

FALLBACK_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "simulation",
    "crystal_waterworld_analyzed_reviews.csv",
)

SAMPLE_REVIEWS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "simulation",
    "sample_reviews",
)

# Dil tespiti desteklenen diller
SUPPORTED_LANGUAGES = ("tr", "en", "de", "ru", "fr", "es", "ar", "it", "nl", "pl", "uk")


class ScraperService:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]

    MIN_DELAY_SEC = 1.5
    MAX_DELAY_SEC = 3.0

    @classmethod
    def _headers(cls) -> dict:
        return {
            "User-Agent": random.choice(cls.USER_AGENTS),
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        }

    @classmethod
    def _sleep(cls):
        time.sleep(random.uniform(cls.MIN_DELAY_SEC, cls.MAX_DELAY_SEC))

    @classmethod
    def _normalize_review(cls, guest_name: str, comment: str, rating, source: str, review_date: str = None, **extra) -> dict:
        r = None
        if rating is not None:
            try:
                r = int(round(float(rating)))
                r = max(1, min(5, r))
            except (TypeError, ValueError):
                r = None
        out = {
            "guest_name": (guest_name or "Anonim").strip()[:80],
            "comment": (comment or "").strip(),
            "rating": r,
            "source": source,
            "review_date": review_date or datetime.now().strftime("%Y-%m-%d"),
            "helpful_count": int(extra.get("helpful_count") or 0),
            "is_most_helpful": bool(extra.get("is_most_helpful")),
            "language": extra.get("language") or cls.detect_language(comment or ""),
        }
        return out

    @classmethod
    def detect_language(cls, comment: str) -> str:
        """Yorum dilini tespit et: tr, en, de, ru, fr, es, ar, vb."""
        if not comment or len(comment.strip()) < 3:
            return "unknown"
        try:
            from langdetect import detect
            lang = detect(comment)
            return lang if lang in SUPPORTED_LANGUAGES else lang[:2]
        except Exception:
            return cls._heuristic_language(comment)

    @classmethod
    def _heuristic_language(cls, text: str) -> str:
        if re.search(r"[ğüşıöçĞÜŞİÖÇ]", text):
            return "tr"
        if re.search(r"[а-яА-ЯёЁ]", text):
            return "ru"
        if re.search(r"[äöüßÄÖÜ]", text):
            return "de"
        if re.search(r"[àâçéèêëîïôùûüÀÂÇÉÈÊËÎÏÔÙÛÜ]", text):
            return "fr"
        if re.search(r"[áéíóúñ¿¡ÁÉÍÓÚÑ]", text):
            return "es"
        if re.search(r"[\u0600-\u06FF]", text):
            return "ar"
        return "en"

    @classmethod
    def _comment_similarity(cls, a: str, b: str) -> float:
        """İki yorum arasındaki benzerlik (0-1)."""
        na = (a or "").strip().lower()
        nb = (b or "").strip().lower()
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        return SequenceMatcher(None, na, nb).ratio()

    @classmethod
    def dedupe_by_similarity(cls, reviews: List[ScrapedReview], threshold: float = 0.85) -> List[ScrapedReview]:
        """Benzer yorumları birleştir (farklı platformlardan aynı yorum)."""
        out: List[ScrapedReview] = []
        for review in reviews:
            is_dup = False
            for existing in out:
                sim = cls._comment_similarity(review.comment, existing.comment)
                if sim >= threshold:
                    is_dup = True
                    # Daha zengin kaydı tut
                    if review.helpful_count > existing.helpful_count:
                        idx = out.index(existing)
                        out[idx] = review
                    break
            if not is_dup:
                out.append(review)
        return out

    @classmethod
    def _sample_csv_path(cls, platform: str) -> Optional[str]:
        path = os.path.join(SAMPLE_REVIEWS_DIR, f"{platform}_sample.csv")
        return path if os.path.isfile(path) else None

    @classmethod
    def scrape_hotel_all_sources(
        cls,
        hotel_name: str,
        google_place_id: str = "",
        urls: Optional[Dict[str, str]] = None,
        *,
        sources: Optional[List[str]] = None,
        city: str = "",
        country: str = "",
        limit_per_source: int = 50,
        google_api_key: str = None,
        serpapi_key: str = None,
        allow_fallback: bool = True,
        analyze: bool = False,
        api_key: str = None,
    ) -> dict:
        """
        Çoklu kaynaktan yorum çek, birleştir, dedup et.
        """
        from app.services.multi_scraper_service import MultiScraperService

        urls = urls or {}
        if sources:
            source_list = sources
        else:
            source_list = []
            if google_place_id or urls.get("google"):
                source_list.append("google")
            for platform in ("booking", "tripadvisor", "agoda", "expedia"):
                if urls.get(platform):
                    source_list.append(platform)
            if not source_list:
                source_list = ["google"]

        merged_urls = dict(urls)
        if google_place_id:
            merged_urls["google"] = google_place_id
            merged_urls["google_place_id"] = google_place_id

        result = MultiScraperService.scrape_hotel(
            name=hotel_name,
            city=city,
            country=country,
            sources=source_list,
            urls=merged_urls,
            options={
                "limit": limit_per_source,
                "analyze": analyze,
                "allow_fallback": allow_fallback,
                "google_places_api_key": google_api_key,
                "api_key": api_key,
                "serpapi_key": serpapi_key,
                "hotel_name": hotel_name,
                "place_id": google_place_id,
            },
        )

        # ScrapedReview formatına dönüştür
        scraped: List[ScrapedReview] = []
        for raw in result.get("reviews", []):
            sr = ScrapedReview(
                hotel_name=raw.get("hotel", hotel_name),
                country=raw.get("country", country),
                city=raw.get("city", city),
                language=raw.get("language", ""),
                platform=Platform.from_string(raw.get("platform", "")).value,
                platform_url=raw.get("source_url", ""),
                review_id=raw.get("review_id", ""),
                date=raw.get("date", ""),
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
                source_detected=Platform.from_string(raw.get("platform", "")).value,
                scrape_method=raw.get("ingestion_method", ""),
            )
            if not sr.language and sr.comment:
                sr.language = cls.detect_language(sr.comment)
            scraped.append(sr)

        deduped = cls.dedupe_by_similarity(scraped)
        deduped.sort(key=lambda r: r.helpful_count, reverse=True)

        source_stats: Dict[str, int] = {}
        for platform in source_list:
            source_stats[platform] = sum(
                1 for r in deduped if Platform.from_string(r.platform).value == platform
            )

        return {
            "reviews": [r.to_dict() for r in deduped],
            "total": len(deduped),
            "raw_total": len(scraped),
            "duplicates_removed": len(scraped) - len(deduped),
            "source_stats": source_stats,
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "methods": result.get("methods", []),
            "sources_succeeded": result.get("sources_succeeded", []),
            "hotel": hotel_name,
            "city": city,
            "country": country,
        }

    @classmethod
    def scrape_serpapi_google_reviews(
        cls, place_id: str, limit: int = 10, api_key: str = None
    ) -> Tuple[List[Dict], Optional[str]]:
        """SerpAPI ile ek Google yorumları (opsiyonel SERPAPI_KEY)."""
        api_key = api_key or os.getenv("SERPAPI_KEY")
        if not api_key:
            return [], "SERPAPI_KEY tanımlı değil."
        try:
            cls._sleep()
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google_maps_reviews",
                    "place_id": place_id,
                    "api_key": api_key,
                    "hl": "tr",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                return [], f"SerpAPI HTTP {resp.status_code}"
            data = resp.json()
            reviews = []
            for item in data.get("reviews", [])[:limit]:
                helpful = item.get("likes") or item.get("helpful_count") or 0
                reviews.append(cls._normalize_review(
                    guest_name=item.get("user", {}).get("name", "Anonim"),
                    comment=item.get("snippet", item.get("extracted_snippet", {}).get("original", "")),
                    rating=item.get("rating"),
                    source="Google (SerpAPI)",
                    review_date=item.get("date", "")[:10] or None,
                ))
                if reviews:
                    reviews[-1]["helpful_count"] = int(helpful)
                    reviews[-1]["language"] = cls.detect_language(reviews[-1].get("comment", ""))
            return reviews, None
        except Exception as e:
            return [], str(e)

    @classmethod
    def detect_source(cls, url: str) -> str:
        u = url.lower()
        if "tripadvisor" in u:
            return "tripadvisor"
        if "booking.com" in u:
            return "booking"
        if "agoda.com" in u:
            return "agoda"
        if "expedia.com" in u:
            return "expedia"
        if "google." in u and ("maps" in u or "place" in u):
            return "google_maps"
        if url.strip().startswith("ChIJ") or "place_id" in u:
            return "google_places"
        return "unknown"

    @classmethod
    def extract_google_place_id(cls, url: str) -> Optional[str]:
        if url.startswith("ChIJ"):
            return url.strip()
        m = re.search(r"place_id[=:]([A-Za-z0-9_-]+)", url)
        if m:
            return m.group(1)
        m = re.search(r"!1s(0x[a-f0-9]+:0x[a-f0-9]+)", url, re.I)
        if m:
            return None  # hex id — Places API farklı format ister
        m = re.search(r"/place/[^/]+/(@|data=).*?1s(ChIJ[A-Za-z0-9_-]+)", url)
        if m:
            return m.group(2)
        m = re.search(r"(ChIJ[A-Za-z0-9_-]{20,})", url)
        if m:
            return m.group(1)
        return None

    @classmethod
    def scrape_google_places_api_v1(cls, place_id: str, limit: int = 10, api_key: str = None) -> Tuple[List[Dict], Optional[str]]:
        """Google Places API (New) — places.googleapis.com/v1"""
        api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return [], "GOOGLE_PLACES_API_KEY tanımlı değil."
        try:
            cls._sleep()
            resp = requests.get(
                f"https://places.googleapis.com/v1/places/{place_id}",
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "reviews,rating,displayName",
                    "Accept-Language": "tr",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return [], f"Places API v1 HTTP {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            reviews = []
            for item in data.get("reviews", [])[:limit]:
                text_obj = item.get("text") or {}
                comment = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)
                author = (item.get("authorAttribution") or {}).get("displayName", "Anonim")
                reviews.append(cls._normalize_review(
                    guest_name=author,
                    comment=comment,
                    rating=item.get("rating"),
                    source="Google Places API",
                    review_date=None,
                ))
            if reviews:
                return reviews, None
            return [], "Places API v1: yorum bulunamadı."
        except Exception as e:
            logger.error(f"Google Places API v1 hatası: {e}")
            return [], str(e)

    @classmethod
    def scrape_google_places_api(cls, place_id: str, limit: int = 10, api_key: str = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Google Places API (Place Details — reviews alanı).
        https://developers.google.com/maps/documentation/places/web-service/details
        """
        api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return [], "GOOGLE_PLACES_API_KEY tanımlı değil."

        try:
            cls._sleep()
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": place_id,
                    "fields": "name,reviews,rating",
                    "reviews_sort": "newest",
                    "key": api_key,
                    "language": "tr",
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != "OK":
                msg = data.get("error_message") or data.get("status")
                logger.warning(f"Google Places API: {msg}")
                return [], msg

            reviews = []
            for item in data.get("result", {}).get("reviews", [])[:limit]:
                reviews.append(cls._normalize_review(
                    guest_name=item.get("author_name", "Anonim"),
                    comment=item.get("text", ""),
                    rating=item.get("rating"),
                    source="Google Places API",
                    review_date=datetime.fromtimestamp(item["time"]).strftime("%Y-%m-%d") if item.get("time") else None,
                ))
            return reviews, None
        except Exception as e:
            logger.error(f"Google Places API hatası: {e}")
            return [], str(e)

    @classmethod
    def fetch_place_id_from_query(cls, query: str, api_key: str = None) -> Tuple[Optional[str], Optional[str]]:
        """Metin araması ile place_id bul (Google Maps link adından veya otel adı)."""
        api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return None, "API anahtarı yok"
        try:
            cls._sleep()
            # Legacy Find Place
            ts = requests.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={
                    "input": query,
                    "inputtype": "textquery",
                    "fields": "place_id,name",
                    "key": api_key,
                    "language": "tr",
                },
                timeout=15,
            ).json()
            cands = ts.get("candidates", [])
            if cands and cands[0].get("place_id"):
                return cands[0]["place_id"], None
            # Text Search (daha geniş)
            ts2 = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": query, "key": api_key, "language": "tr"},
                timeout=15,
            ).json()
            results = ts2.get("results", [])
            if results and results[0].get("place_id"):
                return results[0]["place_id"], None
            return None, ts.get("status") or ts2.get("status") or "Place ID bulunamadı"
        except Exception as e:
            return None, str(e)

    @classmethod
    def scrape_google_places_combined(cls, place_id: str, limit: int = 10, api_key: str = None) -> Tuple[List[Dict], Optional[str]]:
        """Önce legacy, sonra v1 API dene."""
        reviews, err = cls.scrape_google_places_api(place_id, limit, api_key)
        if reviews:
            return reviews, None
        reviews_v1, err_v1 = cls.scrape_google_places_api_v1(place_id, limit, api_key)
        if reviews_v1:
            return reviews_v1, None
        return [], err or err_v1

    @classmethod
    def import_reviews_from_csv(cls, csv_path: str, limit: int = 50) -> Tuple[List[Dict], Optional[str]]:
        """Yerel CSV dosyasından yorum içe aktar."""
        if not os.path.isfile(csv_path):
            return [], f"CSV bulunamadı: {csv_path}"
        rows: List[Dict] = []
        try:
            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return [], "CSV başlık satırı okunamadı"
                for row in reader:
                    comment = (
                        row.get("comment") or row.get("original_comment")
                        or row.get("text") or row.get("review") or row.get("yorum") or ""
                    ).strip()
                    if not comment or len(comment) < 3:
                        continue
                    rating_raw = row.get("rating") or row.get("puan") or row.get("stars")
                    rows.append(cls._normalize_review(
                        guest_name=row.get("guest_name") or row.get("author") or row.get("misafir") or "Anonim",
                        comment=comment,
                        rating=rating_raw,
                        source=row.get("source") or "CSV Import",
                        review_date=(row.get("review_date") or row.get("date") or "")[:10] or None,
                    ))
                    if len(rows) >= limit:
                        break
            if not rows:
                return [], "CSV'de geçerli yorum satırı yok (comment/original_comment sütunu gerekli)"
            return rows, None
        except OSError as e:
            return [], str(e)

    @classmethod
    def _fetch_html(cls, url: str) -> Optional[str]:
        try:
            cls._sleep()
            resp = requests.get(url, headers=cls._headers(), timeout=20)
            if resp.status_code == 403:
                logger.warning(f"403 Forbidden: {url}")
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error(f"HTTP kazıma hatası ({url}): {e}")
            return None

    @classmethod
    def _parse_tripadvisor_json_ld(cls, html: str, limit: int) -> List[Dict]:
        reviews = []
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for block in items:
                    if block.get("@type") == "Review":
                        author = block.get("author", {})
                        name = author.get("name") if isinstance(author, dict) else str(author)
                        rating_val = block.get("reviewRating", {}).get("ratingValue")
                        reviews.append(cls._normalize_review(
                            name, block.get("reviewBody", ""), rating_val, "TripAdvisor",
                            block.get("datePublished", "")[:10] or None,
                        ))
            except (json.JSONDecodeError, TypeError):
                continue
        return reviews[:limit]

    @classmethod
    def _parse_tripadvisor_html(cls, html: str, limit: int) -> List[Dict]:
        reviews = []
        soup = BeautifulSoup(html, "html.parser")

        # TripAdvisor review card selectors (değişebilir)
        selectors = [
            {"card": "div[data-test-target='HR_CC_CARD']", "text": "q", "title": "span"},
            {"card": "div.review-container", "text": "p.partial_entry", "title": "div.info_text"},
        ]

        for sel in selectors:
            cards = soup.select(sel["card"])
            if not cards:
                continue
            for card in cards[:limit]:
                text_el = card.select_one(sel["text"]) or card.find("span", class_=re.compile("review", re.I))
                title_el = card.select_one(sel["title"]) or card.find("a", class_=re.compile("username", re.I))
                comment = text_el.get_text(strip=True) if text_el else ""
                guest = title_el.get_text(strip=True) if title_el else "Misafir"
                bubble = card.select_one("[class*='bubble']") or card
                rating = None
                alt = bubble.find("span", attrs={"class": re.compile("ui_bubble_rating", re.I)})
                if alt and alt.get("class"):
                    for c in alt["class"]:
                        m = re.search(r"bubble_(\d+)", c)
                        if m:
                            rating = int(m.group(1)) // 10
                            break
                if comment:
                    reviews.append(cls._normalize_review(guest, comment, rating, "TripAdvisor"))
            if reviews:
                break

        if not reviews:
            reviews = cls._parse_tripadvisor_json_ld(html, limit)
        return reviews[:limit]

    @classmethod
    def scrape_tripadvisor_reviews(cls, hotel_url: str, limit: int = 10) -> List[Dict]:
        logger.info(f"TripAdvisor kazıma: {hotel_url}")
        html = cls._fetch_html(hotel_url)
        if not html:
            return []
        reviews = cls._parse_tripadvisor_html(html, limit)
        logger.info(f"TripAdvisor: {len(reviews)} yorum bulundu.")
        return reviews

    @classmethod
    def scrape_google_maps_html(cls, url: str, limit: int = 10) -> List[Dict]:
        """Google Maps sayfası — çoğu yorum JS ile yüklenir, sınırlı başarı."""
        logger.info(f"Google Maps HTML kazıma: {url}")
        html = cls._fetch_html(url)
        if not html:
            return []
        reviews = []
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            text = script.string or ""
            if "review" not in text.lower():
                continue
            for m in re.finditer(r'"(text)"\s*:\s*"([^"]{20,500})"', text):
                reviews.append(cls._normalize_review("Google Kullanıcı", m.group(2), None, "Google Maps"))
                if len(reviews) >= limit:
                    break
        return reviews[:limit]

    @classmethod
    def load_fallback_reviews(cls, limit: int = 10) -> List[Dict]:
        """Canlı kazıma başarısız olunca demo yorumları döndür."""
        if os.path.exists(FALLBACK_CSV):
            try:
                rows = []
                with open(FALLBACK_CSV, encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(cls._normalize_review(
                            row.get("guest_name", "Anonim"),
                            row.get("original_comment", row.get("comment", "")),
                            row.get("rating"),
                            row.get("source", "Demo CSV"),
                        ))
                        if len(rows) >= limit:
                            break
                if rows:
                    return rows
            except OSError as e:
                logger.warning(f"Fallback CSV okunamadı: {e}")

        out = []
        for item in FALLBACK_REVIEWS[:limit]:
            out.append(cls._normalize_review(
                item["guest_name"], item["comment"], item["rating"], item["source"]
            ))
        return out

    @classmethod
    def scrape_reviews(
        cls,
        url: str,
        limit: int = 10,
        allow_fallback: bool = True,
        google_api_key: str = None,
        csv_path: str = None,
    ) -> dict:
        """
        Ana giriş noktası. URL, CSV veya Google Places API ile yorum çeker.
        google_api_key: UI/CLI'den gelen Places API anahtarı (env'den öncelikli değil — explicit key wins)
        """
        limit = max(1, min(limit, 50))
        api_key = google_api_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")

        # 0) CSV içe aktarma
        if csv_path or (url and url.lower().startswith("csv:")):
            path = csv_path or url[4:].strip()
            imported, err = cls.import_reviews_from_csv(path, limit)
            if imported:
                return {
                    "reviews": imported,
                    "total": len(imported),
                    "method": "csv_import",
                    "source_detected": "csv",
                    "warning": f"CSV'den {len(imported)} yorum içe aktarıldı: {path}",
                }
            return {
                "reviews": [],
                "total": 0,
                "method": "csv_import_failed",
                "source_detected": "csv",
                "warning": err or "CSV içe aktarma başarısız.",
            }

        source = cls.detect_source(url)
        method = "live"
        warning = None
        reviews: List[Dict] = []

        # 1) Google Places API — place_id veya Maps linki (API key varsa öncelik)
        place_id = cls.extract_google_place_id(url)
        if (place_id or source == "google_maps" or source == "google_places") and api_key:
            if not place_id and source == "google_maps":
                name_match = re.search(r"/place/([^/@?]+)", url)
                query = unquote(name_match.group(1).replace("+", " ")) if name_match else url
                place_id, pid_err = cls.fetch_place_id_from_query(query, api_key)
                if pid_err and not place_id:
                    warning = f"Place ID arama: {pid_err}"

            if place_id:
                api_reviews, err = cls.scrape_google_places_combined(place_id, limit, api_key)
                if api_reviews:
                    note = (
                        f"Google Places API ile {len(api_reviews)} gerçek yorum çekildi. "
                        "(Google en fazla ~5 yorum döndürür — tam arşiv için CSV import kullanın.)"
                    )
                    return {
                        "reviews": api_reviews,
                        "total": len(api_reviews),
                        "method": "google_places_api",
                        "source_detected": "google",
                        "warning": note,
                    }
                if err:
                    warning = f"Google Places API: {err}"
        elif (place_id or source == "google_maps") and not api_key:
            warning = (
                "GOOGLE_PLACES_API_KEY tanımlı değil. "
                "Web UI'daki 'Google Places API Key' alanına veya ortam değişkenine anahtar girin."
            )

        # API key yoksa veya başarısız — eski place_id arama (env only)
        if not reviews and (place_id or source == "google_maps"):
            if not place_id and source == "google_maps":
                env_key = os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
                if env_key:
                    name_match = re.search(r"/place/([^/@]+)", url)
                    query = unquote(name_match.group(1).replace("+", " ")) if name_match else "hotel"
                    place_id, _ = cls.fetch_place_id_from_query(query, env_key)

            if place_id:
                api_reviews, err = cls.scrape_google_places_combined(place_id, limit, api_key)
                if api_reviews:
                    return {
                        "reviews": api_reviews,
                        "total": len(api_reviews),
                        "method": "google_places_api",
                        "source_detected": "google",
                        "warning": "Google Places API (ortam değişkeni) ile çekildi.",
                    }
                if err and not warning:
                    warning = f"Google Places API: {err}"

        # 2) TripAdvisor HTML
        if source == "tripadvisor":
            reviews = cls.scrape_tripadvisor_reviews(url, limit)
            if reviews:
                return {
                    "reviews": reviews,
                    "total": len(reviews),
                    "method": "tripadvisor_html",
                    "source_detected": "tripadvisor",
                    "warning": "TripAdvisor HTML kazıması — ToS riski; üretimde API kullanın.",
                }

        # 3) Google Maps HTML (son çare)
        if source == "google_maps" and not reviews:
            reviews = cls.scrape_google_maps_html(url, limit)
            if reviews:
                return {
                    "reviews": reviews,
                    "total": len(reviews),
                    "method": "google_maps_html",
                    "source_detected": "google",
                    "warning": "Google Maps HTML — kısmi veri; Places API önerilir.",
                }

        # 4) Fallback (demo) — API key varken varsayılan kapalı önerilir
        if allow_fallback:
            reviews = cls.load_fallback_reviews(limit)
            api_hint = (
                " Gerçek Google yorumları için GOOGLE_PLACES_API_KEY tanımlayın "
                "(Google Cloud Console → Places API)."
            )
            return {
                "reviews": reviews,
                "total": len(reviews),
                "method": "fallback_demo",
                "source_detected": source,
                "warning": (
                    (warning + " — " if warning else "")
                    + "Canlı kazıma başarısız. Demo yorumlar yüklendi."
                    + api_hint
                ),
            }

        return {
            "reviews": [],
            "total": 0,
            "method": "failed",
            "source_detected": source,
            "warning": warning or "Yorum çekilemedi.",
        }


# --- Platform scraper sınıfları (adaptör delegasyonu) ---

class BookingScraper:
    """Booking.com — CSV import veya demo fallback."""

    @classmethod
    def scrape(cls, url: str, hotel_name: str, limit: int = 10, allow_fallback: bool = True) -> Tuple[List[Dict], str]:
        from app.services.scraper_adapters.booking_adapter import BookingAdapter

        sample = ScraperService._sample_csv_path("booking")
        csv_path = url if url and os.path.isfile(url) else sample if allow_fallback else None
        result = BookingAdapter().fetch_reviews(hotel_name, {
            "csv_path": csv_path,
            "limit": limit,
            "allow_fallback": allow_fallback,
            "hotel_name": hotel_name,
        })
        reviews = [r.to_legacy_dict() for r in result.reviews]
        warning = result.warning or result.error or ""
        return reviews, warning


class TripAdvisorScraper:
    """TripAdvisor — gelişmiş headers, 403 durumunda CSV önerisi."""

    ENHANCED_HEADERS = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://www.tripadvisor.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        },
    ]

    @classmethod
    def scrape(cls, url: str, hotel_name: str, limit: int = 10, allow_fallback: bool = True) -> Tuple[List[Dict], str]:
        from app.services.scraper_adapters.tripadvisor_adapter import TripAdvisorAdapter

        result = TripAdvisorAdapter().fetch_reviews(hotel_name, {
            "url": url,
            "urls": {"tripadvisor": url},
            "limit": limit,
            "allow_fallback": allow_fallback,
            "hotel_name": hotel_name,
        })
        if not result.reviews and allow_fallback:
            sample = ScraperService._sample_csv_path("tripadvisor")
            if sample:
                from app.services.scraper_adapters.csv_import_adapter import CsvImportAdapter
                csv_result = CsvImportAdapter().fetch_reviews(hotel_name, {
                    "csv_path": sample, "limit": limit, "platform": "TripAdvisor",
                })
                result.reviews = csv_result.reviews
                result.warning = (
                    "TripAdvisor 403 bot koruması — demo CSV yüklendi. "
                    "Gerçek veri için tripadvisor_sample.csv formatında CSV import kullanın."
                )
        reviews = [r.to_legacy_dict() for r in result.reviews]
        warning = result.warning or result.error or ""
        return reviews, warning


class AgodaScraper:
    """Agoda — stub + demo CSV fallback."""

    @classmethod
    def scrape(cls, url: str, hotel_name: str, limit: int = 10, allow_fallback: bool = True) -> Tuple[List[Dict], str]:
        from app.services.scraper_adapters.agoda_adapter import AgodaScraper as AgodaAdapter

        result = AgodaAdapter().fetch_reviews(hotel_name, {
            "url": url,
            "urls": {"agoda": url},
            "limit": limit,
            "allow_fallback": allow_fallback,
            "hotel_name": hotel_name,
        })
        reviews = [r.to_legacy_dict() for r in result.reviews]
        warning = result.warning or result.error or ""
        return reviews, warning


class ExpediaScraper:
    """Expedia — stub + demo CSV fallback."""

    @classmethod
    def scrape(cls, url: str, hotel_name: str, limit: int = 10, allow_fallback: bool = True) -> Tuple[List[Dict], str]:
        from app.services.scraper_adapters.expedia_adapter import ExpediaScraper as ExpediaAdapter

        result = ExpediaAdapter().fetch_reviews(hotel_name, {
            "url": url,
            "urls": {"expedia": url},
            "limit": limit,
            "allow_fallback": allow_fallback,
            "hotel_name": hotel_name,
        })
        reviews = [r.to_legacy_dict() for r in result.reviews]
        warning = result.warning or result.error or ""
        return reviews, warning
