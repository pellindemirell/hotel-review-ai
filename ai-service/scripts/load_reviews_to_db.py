#!/usr/bin/env python3
"""Normalize edilmiş yorum dosyalarını doğrudan veritabanına yükler.

Neden HTTP yerine doğrudan DB
-----------------------------
POST /api/reviews/import yolu satır başına bir SaveChangesAsync yapıyor
(1 Review + 1 AnalysisJob + ~2 AuditLog) ve JWT gerektiriyor. 2496 satır için
bu hem yavaş hem de yükleme yarıda kesilirse kısmi veri bırakıyor.

Bu script CreateReviewHandler.cs'in yaptığının BİREBİR aynısını yapar —
her yorum için bir Reviews satırı ve bir AnalysisJobs satırı — ama hepsini
tek transaction'da. Arka plandaki AnalysisBackgroundWorker kuyruğu aynen
görür ve analiz eder; bu script AI tarafına hiç dokunmaz.

Fark: AuditLogs yazılmaz. AuditInterceptor yalnızca EF üzerinden geçen
değişikliklerde çalışıyor. Toplu veri yüklemesi kullanıcı etkinliği olmadığı
için bu istenen davranış.

Kullanım
--------
    ai-service/.venv/bin/python ai-service/scripts/load_reviews_to_db.py --dry-run
    ai-service/.venv/bin/python ai-service/scripts/load_reviews_to_db.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values, register_uuid

# uuid.UUID nesnelerinin parametre olarak geçirilebilmesi için şart.
register_uuid()

csv.field_size_limit(10 * 1024 * 1024)

# Bağlantı bilgisi ortamdan gelir; üretim şifresi koda gömülü değil.
DEFAULT_DSN = os.getenv("REVIEWS_DB_URL") or os.getenv("DATABASE_URL")
if DEFAULT_DSN and DEFAULT_DSN.startswith("postgresql+asyncpg://"):
    # Bu script psycopg2 kullanıyor; asyncpg sürücü ekini kaldır.
    DEFAULT_DSN = DEFAULT_DSN.replace("postgresql+asyncpg://", "postgresql://", 1)

# Dosya adı -> Hotels."Name". Kimlikler koda gömülmüyor, isimden okunuyor;
# böylece yanlış otele yazma riski tek bir yerde ve gözle görülür kalıyor.
FILE_TO_HOTEL = {
    "adoraresort": "Adora Hotel & Resort",
    "crystalhotel": "Crystal Waterworld Resort & Spa",
    "megasaray": "Megasaray Club Belek",
    "rixosbelek": "Rixos Premium Belek",
    "titanicbelek": "Titanic Deluxe Golf Belek",
}

# ReviewSource.Import (Domain/Enums/ReviewSource.cs: Manual=0, Import=1, Mobile=2, Api=3)
SOURCE_IMPORT = 1
# AnalysisJobStatus.Pending
STATUS_PENDING = 0

# ImportReviewsCsvCommand.cs:232 — boş isim "Misafir" oluyor
DEFAULT_GUEST_NAME = "Misafir"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve()
    default_dir = here.parents[2] / "reviews" / "normalized"

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-dir", type=Path, default=default_dir)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true", help="bağlan ve doğrula, ama yazma")
    parser.add_argument("--only", action="append", default=[], metavar="AD",
                        help="sadece bu dosyayı yükle (birden çok kez verilebilir)")
    args = parser.parse_args(argv)

    if not args.dsn:
        print(
            "HATA: veritabanı adresi yok. REVIEWS_DB_URL ya da DATABASE_URL "
            "ortam değişkenini tanımlayın veya --dsn ile verin.",
            file=sys.stderr,
        )
        return 2

    wanted = set(args.only) if args.only else set(FILE_TO_HOTEL)
    unknown = wanted - set(FILE_TO_HOTEL)
    if unknown:
        print(f"HATA: tanımsız dosya adı: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # --- otel kimliklerini isimden çöz ---
            cur.execute('SELECT "Name", "Id" FROM public."Hotels";')
            hotels = {name: hotel_id for name, hotel_id in cur.fetchall()}

            missing = [h for f, h in FILE_TO_HOTEL.items() if f in wanted and h not in hotels]
            if missing:
                print(f"HATA: veritabanında bulunamayan otel: {missing}", file=sys.stderr)
                return 2

            total_reviews = 0
            summary: list[tuple[str, str, int, int]] = []

            for stem in sorted(wanted):
                hotel_name = FILE_TO_HOTEL[stem]
                hotel_id = hotels[hotel_name]
                path = args.in_dir / f"{stem}.csv"

                if not path.is_file():
                    print(f"HATA: dosya yok: {path}", file=sys.stderr)
                    return 2

                # --- mükerrer yükleme koruması ---
                cur.execute('SELECT count(*) FROM public."Reviews" WHERE "HotelId" = %s;', (hotel_id,))
                existing = cur.fetchone()[0]
                if existing > 0:
                    print(
                        f"HATA: {hotel_name} otelinde zaten {existing} yorum var. "
                        f"Mükerrer kayıt oluşmasın diye durduruluyor.",
                        file=sys.stderr,
                    )
                    return 2

                rows = read_rows(path)
                review_values = []
                job_values = []

                for row in rows:
                    review_id = uuid.uuid4()
                    guest_name = (row.get("GuestName") or "").strip() or DEFAULT_GUEST_NAME
                    comment = row.get("Comment") or ""
                    language = (row.get("Language") or "").strip() or "tr"
                    rating = int(row["Rating"])
                    review_date = datetime.fromisoformat(row["ReviewDate"].replace("Z", "+00:00"))

                    # Domain kuralları (Review.Create) — burada da uygulanıyor ki
                    # geçersiz satır sessizce veritabanına girmesin.
                    if len(comment.strip()) < 10:
                        print(f"HATA: {path.name}: 10 karakterden kısa yorum var.", file=sys.stderr)
                        return 2
                    if not 1 <= rating <= 5:
                        print(f"HATA: {path.name}: geçersiz puan {rating}.", file=sys.stderr)
                        return 2

                    review_values.append((
                        review_id, SOURCE_IMPORT, guest_name[:200], comment, language[:10],
                        rating, review_date, None, now, None, True, hotel_id,
                    ))
                    job_values.append((
                        uuid.uuid4(), review_id, STATUS_PENDING, 0, None, None, now, None, True,
                    ))

                if not args.dry_run:
                    execute_values(cur, """
                        INSERT INTO public."Reviews"
                            ("Id","Source","GuestName","Comment","Language","Rating",
                             "ReviewDate","CreatedBy","CreatedAt","UpdatedAt","IsActive","HotelId")
                        VALUES %s
                    """, review_values, page_size=500)

                    execute_values(cur, """
                        INSERT INTO public."AnalysisJobs"
                            ("Id","ReviewId","Status","RetryCount","ErrorMessage",
                             "ProcessedAt","CreatedAt","UpdatedAt","IsActive")
                        VALUES %s
                    """, job_values, page_size=500)

                total_reviews += len(review_values)
                summary.append((stem, hotel_name, len(review_values), len(job_values)))
                print(f"  {stem:14} -> {hotel_name:32} {len(review_values):5} yorum")

            print()
            print(f"Toplam: {total_reviews} yorum + {total_reviews} analiz işi")

            if args.dry_run:
                conn.rollback()
                print("(dry-run — hiçbir şey yazılmadı)")
                return 0

            conn.commit()
            print("YAZILDI (commit).")

            # --- yazma sonrası doğrulama ---
            with conn.cursor() as check:
                check.execute("""
                    SELECT h."Name", count(r."Id"),
                           min(r."ReviewDate")::date, max(r."ReviewDate")::date,
                           count(DISTINCT date_trunc('day', r."ReviewDate"))
                      FROM public."Hotels" h
                      LEFT JOIN public."Reviews" r ON r."HotelId" = h."Id"
                     GROUP BY 1 ORDER BY 1;
                """)
                print()
                print(f"{'Otel':34} {'yorum':>6} {'ilk':>12} {'son':>12} {'farkli gun':>11}")
                for name, count, first, last, days in check.fetchall():
                    print(f"{name:34} {count:>6} {str(first):>12} {str(last):>12} {days:>11}")

                check.execute('SELECT "Status", count(*) FROM public."AnalysisJobs" GROUP BY 1 ORDER BY 1;')
                print()
                print("AnalysisJobs (0=Pending 1=Processing 2=Completed 3=Failed):")
                for status, count in check.fetchall():
                    print(f"  {status}: {count}")

        return 0

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
