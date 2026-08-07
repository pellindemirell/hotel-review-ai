"""Google Maps Playwright tabanlı yorum kazıma adaptörü.

Otomasyon klasöründeki Playwright scraper'ı subprocess olarak çalıştırır,
çıktı CSV'sini okuyup IngestedReview listesine dönüştürür.
"""

from __future__ import annotations

import logging

import csv
import os
import re
import sqlite3
import subprocess
import tempfile
from typing import Any, Optional
from urllib.parse import unquote_plus

from app.services.review_ingestion_schema import IngestedReview
from .base import BaseScraperAdapter, AdapterResult

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_DIR)))
OTOMASYON_DIR = os.path.join(
    os.path.dirname(_PROJECT_BASE),
    "otomasyon",
    "otomasyon",
)

OTOMASYON_DB = os.path.join(OTOMASYON_DIR, "reviews.db")
OTOMASYON_MAIN = os.path.join(OTOMASYON_DIR, "main.py")


def _extract_hotel_name(url: str) -> str:
    """Google Maps URL'inden otel adını çıkarır."""
    m = re.search(r"/maps/place/([^/@?]+)", url)
    if m:
        return unquote_plus(m.group(1)).strip()[:100]
    return ""


class GoogleMapsPlaywrightAdapter(BaseScraperAdapter):
    source_id = "google_maps_playwright"
    display_name = "Google Maps (Playwright Browser)"

    def legal_info(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.display_name,
            "status": "allowed",
            "method": "playwright_browser",
            "recommended": True,
            "warning": (
                "Google Maps sayfalarını gerçek bir Chromium tarayıcı ile açar, "
                "kaydırır ve yorumları yapısal olarak çıkarır. Google Places API'den "
                "farklı olarak 1500+ yorum toplayabilir. Google ToS'e tabidir."
            ),
            "capacity": "1500+ yorum / sıralama, 4 sıralama ile 6000+",
            "requirements": "playwright, chromium browser",
        }

    def fetch_reviews(
        self,
        hotel_query: str,
        options: dict[str, Any],
    ) -> AdapterResult:
        url = options.get("url") or hotel_query
        search = options.get("search", "")
        max_reviews = options.get("limit", 0)
        all_sorts = options.get("all_sorts", True)
        hotel_name = _extract_hotel_name(url)

        # 1) Önce otomasyon DB'sinde bu otele ait yorum var mı kontrol et
        existing = self._read_from_otomasyon_db(hotel_name)
        if existing:
            return AdapterResult(
                reviews=existing,
                method="google_maps_db_cache",
                legal_notice=self.legal_info().get("warning", ""),
            )

        # 2) Yoksa Playwright ile dene
        result = self._run_playwright(url, search, max_reviews, all_sorts)

        # 3) Playwright hata döndüyse kullanıcıya bildir
        if result.error and not result.reviews:
            result.warning = "Google Maps şu anda bu otelin yorumlarını göstermiyor. IP sınırlandırması veya sayfa yapısı değişikliği olabilir. Daha sonra tekrar deneyin."

        return result

    def _read_from_otomasyon_db(self, hotel_filter: str = "") -> list[IngestedReview]:
        if not os.path.exists(OTOMASYON_DB):
            return []
        try:
            conn = sqlite3.connect(OTOMASYON_DB, timeout=10)
            if hotel_filter:
                like = f"%{hotel_filter}%"
                rows = conn.execute(
                    "SELECT author, rating, review_text, date_approx, likes, review_id "
                    "FROM reviews WHERE business LIKE ? ORDER BY date_approx DESC LIMIT 200",
                    (like,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT author, rating, review_text, date_approx, likes, review_id "
                    "FROM reviews ORDER BY date_approx DESC LIMIT 200"
                ).fetchall()
            conn.close()
            reviews = []
            for r in rows:
                comment = (r[2] or "").strip()
                if not comment:
                    continue
                reviews.append(self._make_review(
                    comment=comment,
                    rating=float(r[1]) if r[1] else 0.0,
                    guest_name=r[0] or "Anonim",
                    date=r[3] or "",
                    platform="Google Maps",
                    helpful_count=int(r[4] or 0),
                    review_id=r[5] or "",
                    ingestion_method=self.source_id + "_db",
                ))
            return reviews
        except Exception:
            return []

    def _run_playwright(
        self,
        url: str,
        search: str = "",
        max_reviews: int = 0,
        all_sorts: bool = True,
    ) -> AdapterResult:
        if not os.path.exists(OTOMASYON_MAIN):
            return AdapterResult(error=f"Playwright scraper bulunamadı: {OTOMASYON_MAIN}")

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False, mode="w", encoding="utf-8", newline=""
            ) as tmp:
                tmp_path = tmp.name

            cmd = ["python", OTOMASYON_MAIN]
            if search:
                cmd += ["--search", search]
            else:
                cmd.append(url)
            cmd += ["--max", str(max_reviews), "--format", "csv", "-o", tmp_path.replace(".csv", "")]
            if all_sorts:
                cmd.append("--all-sorts")
            cmd.append("--no-headless")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            timeout_secs = 600 if all_sorts else 180
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_secs,
                env=env, cwd=OTOMASYON_DIR,
            )

            reviews = self._parse_csv(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                logging.getLogger(__name__).debug("_run_playwright: hata yutuldu", exc_info=True)

            for r in reviews:
                r.ingestion_method = self.source_id
                r.legal_notice = self.legal_info().get("warning", "")

            warning = None
            output = (proc.stdout or "") + (proc.stderr or "")
            if not reviews:
                if "Yorum kartları görünmedi" in output:
                    warning = "Google Maps yorum paneli yüklenemedi. IP sınırlandırması olabilir, daha sonra tekrar deneyin."
                elif "bulunamadı" in output.lower():
                    warning = "Bu otel için Google Maps'te yorum bulunamadı."
                else:
                    warning = "Google Maps yorumları şu anda alınamıyor. Lütfen daha sonra tekrar deneyin."

            return AdapterResult(
                reviews=reviews,
                warning=warning,
                method="playwright_browser",
                legal_notice=self.legal_info().get("warning", ""),
            )

        except subprocess.TimeoutExpired:
            return AdapterResult(error=f"Google Maps çok yavaş yanıt verdi (zaman aşımı: {timeout_secs}s). Daha sonra tekrar deneyin.")
        except Exception as e:
            return AdapterResult(error=f"Playwright scraper hatası: {e}")

    def _parse_csv(self, csv_path: str) -> list[IngestedReview]:
        actual = csv_path.replace(".csv", "") + ".csv"
        if not os.path.exists(actual):
            actual = csv_path
        if not os.path.exists(actual):
            return []

        reviews = []
        with open(actual, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                comment = row.get("Yorum Metni") or row.get("review_text") or ""
                if not comment.strip():
                    continue
                try:
                    rating = float(row.get("Puan (Yıldız)") or row.get("rating") or 0)
                except (ValueError, TypeError):
                    rating = 0.0
                reviews.append(self._make_review(
                    comment=comment,
                    rating=rating,
                    guest_name=row.get("Kullanıcı Adı") or row.get("author") or "Anonim",
                    date=row.get("Tarih (Yaklaşık)") or row.get("date_approx") or row.get("date_text") or "",
                    platform="Google Maps",
                    helpful_count=int(row.get("Beğeni") or row.get("likes") or 0),
                    review_id=row.get("Yorum ID") or row.get("review_id") or "",
                    ingestion_method=self.source_id,
                ))
        return reviews
