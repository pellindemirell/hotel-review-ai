#!/usr/bin/env python3
"""Google Maps scraper çıktısını içe aktarılabilir hale getirir.

Neden gerekli
-------------
Google Maps mutlak tarih vermiyor; "a month ago" gibi göreli ifadeler dönüyor ve
scraper bunları tek bir güne yuvarlamış. Sonuç: dosya başına 11-14 farklı tarih,
846 satır tek bir etikette. Bu haliyle panelin "Puan Trendi" grafiği birkaç dikey
sütuna, "Son 7/30/90 gün" filtreleri de kümelenmiş sonuçlara dönüyor.

Ayrıca .NET içe aktarıcısının (ImportReviewsCsvCommand.cs) CSV dalı sütunları
yalnızca İngilizce C# property adlarıyla eşliyor, yani Türkçe başlıklı ham CSV
sıfır satır aktarıyor.

Bu script her iki sorunu da çözer ve orijinal dosyalara dokunmadan
reviews/normalized/ altına yükleme için hazır dosyalar üretir.

Bu TEK SEFERLİK bir düzeltmedir; kalıcı içe aktarıcı mantığı değildir. Scraper
gerçek tarihi yakalayacak şekilde düzeltildiğinde bu adım gereksiz hale gelir.

Kullanım
--------
    ai-service/.venv/bin/python ai-service/scripts/normalize_scraped_reviews.py --dry-run
    ai-service/.venv/bin/python ai-service/scripts/normalize_scraped_reviews.py
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Yorum metinleri 4500 karaktere kadar çıkıyor; csv modülünün varsayılan alan
# sınırı buna yetiyor ama ileride daha uzun yorumlar gelirse patlamasın.
csv.field_size_limit(10 * 1024 * 1024)

# Kaynak sütun adları (scraper çıktısı)
SRC_NAME = "Kullanıcı Adı"
SRC_RATING = "Puan (Yıldız)"
SRC_COMMENT = "Yorum Metni"
SRC_RELATIVE = "Tarih (Metin)"
SRC_APPROX = "Tarih (Yaklaşık)"
SRC_ID = "Yorum ID"

# Hedef sütunlar. Bunlar .NET tarafındaki CsvReviewRecord property adlarının
# birebir aynısı; sırası da Excel dalının konumsal yedeğiyle uyumlu. Fazladan
# sütun EKLENMEMELİ: örneğin "OriginalRelativeDate" içinde "date" geçtiği için
# Excel'in bulanık eşleyicisini zehirler.
OUT_COLUMNS = ["GuestName", "Comment", "Rating", "ReviewDate", "Source", "Language"]

# .NET tarafında Comment için asgari uzunluk kontrolü (CreateReviewValidator ve
# Review.Create). Bu satırları burada eleyip frontend'in sınırsız hata listesi
# basmasını engelliyoruz.
MIN_COMMENT_LEN = 10

MINUTE = 60.0
HOUR = 60 * MINUTE
DAY = 24 * HOUR

_UNIT_SECONDS = {
    "minute": MINUTE,
    "hour": HOUR,
    "day": DAY,
    "week": 7 * DAY,
    "month": 30 * DAY,
    "year": 365 * DAY,
}

_RELATIVE_RE = re.compile(
    r"^(?P<count>\d+|an?|one)\s+(?P<unit>minute|hour|day|week|month|year)s?\s+ago$",
    re.IGNORECASE,
)
_EDITED_RE = re.compile(r"^\s*edited\s+", re.IGNORECASE)


class UnparseableRelativeDate(ValueError):
    """Merdivende karşılığı olmayan göreli tarih ifadesi."""


def parse_relative(text: str) -> tuple[str, float, float]:
    """Göreli ifadeyi (normalize etiket, alt sınır, üst sınır) üçlüsüne çevirir.

    Google aşağı yuvarladığı için her etiket bir *yaş aralığı* demektir:
    "a month ago" = 30-59 gün arası. Sınırlar saniye cinsinden döner ve
    aralık yarı açıktır: [lo, hi).

    Hafta/ay sınırındaki tek belirsiz nokta "4 weeks ago" (28-29 gün) ile
    "a month ago" (30+ gün) arasıdır; merdiven bitişik tutulduğu için bu
    seçim sıralamayı bozmaz.
    """
    cleaned = _EDITED_RE.sub("", text or "").strip()
    match = _RELATIVE_RE.match(cleaned)
    if not match:
        raise UnparseableRelativeDate(text)

    raw_count = match.group("count").lower()
    count = 1 if raw_count in ("a", "an", "one") else int(raw_count)
    unit = match.group("unit").lower()

    if count < 1:
        raise UnparseableRelativeDate(text)

    label = f"{count} {unit}{'s' if count != 1 else ''} ago"
    step = _UNIT_SECONDS[unit]

    lo = count * step
    hi = (count + 1) * step

    # Hafta ve ay merdivenlerini birbirine bitiştir: 4 hafta 28. günde başlar
    # ama 30. günde "a month ago"a devrettiği için orada biter.
    if unit == "week" and count == 4:
        hi = 30 * DAY

    return label, lo, hi


def label_for_age(age_seconds: float) -> str:
    """parse_relative'in tersi — doğrulama için kullanılır."""
    for unit, step, upper in (
        ("minute", MINUTE, HOUR),
        ("hour", HOUR, DAY),
        ("day", DAY, 7 * DAY),
        ("week", 7 * DAY, 30 * DAY),
        ("month", 30 * DAY, 365 * DAY),
        ("year", 365 * DAY, math.inf),
    ):
        if age_seconds < upper:
            count = int(age_seconds // step)
            count = max(count, 1)
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    raise AssertionError("ulaşılamaz")


def round_half_up(value: float) -> int:
    """Python'un round()'u bankacı yuvarlaması yapar (4.5 -> 4).

    Puanlarda bunu istemiyoruz: 4.5 -> 5 olmalı.
    """
    return int(math.floor(value + 0.5))


def parse_rating(raw: str) -> int | None:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return max(1, min(5, round_half_up(value)))


# Türkçeye özgü harfler. ç/ö/ü kasıtlı olarak yok — Almanca ve Fransızca'da da
# geçiyorlar, ayırt edici değiller.
_TURKISH_CHARS = set("ığşİĞŞı")
_TURKISH_WORDS = re.compile(
    r"\b(ve|çok|için|bir|ama|otel|güzel|değil|bu|da|de|ile|her|daha|"
    r"personel|temiz|yemek|teşekkür|kesinlikle|tavsiye)\b",
    re.IGNORECASE,
)
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_ARABIC = re.compile(r"[؀-ۿ]")

# Antalya otel yorumlarında gerçekten görülebilecek Latin alfabeli diller.
# Bunun dışındaki her tespit gürültü sayılıp 'en'e düşürülür.
_PLAUSIBLE_LATIN = {
    "en", "de", "nl", "fr", "es", "it", "pl", "ro",
    "sv", "da", "fi", "hu", "cs", "sk", "et", "lv", "lt",
}

# langdetect kısa metinlerde güvenilmez: ölçtüm, "Good hotel" -> af (p=1.00),
# "Cool amazing super puper" -> it (p=1.00). Bu eşiklerin altında tespite
# güvenmiyoruz.
_MIN_DETECT_LEN = 60
_MIN_DETECT_PROB = 0.95


def build_language_detector():
    """Dil kodu üretir; langdetect'in kısa metin gürültüsünü filtreler.

    Bu alan analiz kalitesini etkilemiyor — AI servisi (translation_service.py)
    dili kendisi tespit ediyor ve gelen değeri yalnızca tespit başarısız olursa
    ipucu olarak kullanıyor. Buradaki değer panelde görünen/filtrelenen veri,
    o yüzden yanlış olmaması yeterli; aşırı hassas olması gerekmiyor.
    """
    try:
        from langdetect import DetectorFactory, detect_langs  # type: ignore
    except ImportError:
        return None

    DetectorFactory.seed = 0

    def detector(text: str) -> str:
        if _TURKISH_CHARS & set(text) or _TURKISH_WORDS.search(text):
            return "tr"
        if _CYRILLIC.search(text):
            return "ru"
        if _ARABIC.search(text):
            return "ar"

        try:
            top = detect_langs(text)[0]
        except Exception:
            return "en"

        if (
            top.lang in _PLAUSIBLE_LATIN
            and len(text) >= _MIN_DETECT_LEN
            and top.prob >= _MIN_DETECT_PROB
        ):
            return top.lang
        return "en"

    return detector


@dataclass
class Row:
    index: int
    guest_name: str
    comment: str
    rating: int | None
    relative_raw: str
    label: str
    lo: float
    hi: float
    review_id: str
    timestamp: datetime | None = None
    language: str = "tr"


@dataclass
class FileReport:
    path: Path
    anchor: datetime
    total: int = 0
    dropped_empty: int = 0
    dropped_short: int = 0
    dropped_duplicate: int = 0
    unparseable: list[str] = field(default_factory=list)
    order_breaks: list[str] = field(default_factory=list)
    blank_rating: int = 0
    buckets: list[tuple[str, int, datetime, datetime]] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    monotonic_ok: bool = False
    roundtrip_ok: bool = False
    kept: int = 0


def read_source(path: Path) -> list[dict[str, str]]:
    # Kaynak dosyalar BOM'lu; utf-8-sig BOM'u temizler.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_file(
    path: Path,
    anchor: datetime,
    spread: bool,
    detector,
) -> tuple[list[Row], FileReport]:
    report = FileReport(path=path, anchor=anchor)
    raw_rows = read_source(path)
    report.total = len(raw_rows)

    seen_ids: set[str] = set()
    kept: list[Row] = []

    for index, raw in enumerate(raw_rows):
        comment = (raw.get(SRC_COMMENT) or "").replace("\r\n", "\n").strip()

        if not comment:
            report.dropped_empty += 1
            continue
        if len(comment) < MIN_COMMENT_LEN:
            report.dropped_short += 1
            continue

        review_id = (raw.get(SRC_ID) or "").strip()
        if review_id:
            if review_id in seen_ids:
                report.dropped_duplicate += 1
                continue
            seen_ids.add(review_id)

        relative_raw = (raw.get(SRC_RELATIVE) or "").strip()
        try:
            label, lo, hi = parse_relative(relative_raw)
        except UnparseableRelativeDate:
            report.unparseable.append(f"satır {index + 2}: {relative_raw!r}")
            continue

        rating = parse_rating(raw.get(SRC_RATING, ""))
        if rating is None:
            report.blank_rating += 1

        kept.append(
            Row(
                index=index,
                guest_name=(raw.get(SRC_NAME) or "").strip(),
                comment=comment,
                rating=rating,
                relative_raw=relative_raw,
                label=label,
                lo=lo,
                hi=hi,
                review_id=review_id,
            )
        )

    report.kept = len(kept)

    # --- Kova sırası kontrolü -------------------------------------------------
    # Dosya yeniden eskiye sıralı olmalı. Öyleyse kovaların dosya sırasındaki
    # yaşları azalmamalı. Bozuksa global sıralama garantisi düşer; rapora yazıp
    # doğrulamayı düşürüyoruz.
    previous_lo = -1.0
    for row in kept:
        if row.lo < previous_lo:
            report.order_breaks.append(
                f"satır {row.index + 2}: {row.label!r} önceki kovadan daha yeni"
            )
        previous_lo = max(previous_lo, row.lo)

    # --- Zaman damgası üretimi ------------------------------------------------
    # Her kovadaki satırlar, kova aralığına DOSYA SIRASIYLA eşit dağıtılır:
    #     age_k = lo + (hi - lo) * (k + 0.5) / n
    # (k + 0.5) sınıra tam oturmayı engeller, böylece damga geri çevrildiğinde
    # etiket kaymaz. Aralıklar bitişik ve ayrık olduğu için global azalan sıra
    # kendiliğinden korunur.
    grouped: dict[str, list[Row]] = {}
    for row in kept:
        grouped.setdefault(row.label, []).append(row)

    for label, rows in grouped.items():
        count = len(rows)
        for position, row in enumerate(rows):
            if spread:
                age = row.lo + (row.hi - row.lo) * (position + 0.5) / count
            else:
                age = row.lo
            row.timestamp = (anchor - timedelta(seconds=age)).replace(microsecond=0)

    for label, rows in grouped.items():
        stamps = [r.timestamp for r in rows if r.timestamp]
        if stamps:
            report.buckets.append((label, len(rows), min(stamps), max(stamps)))
    report.buckets.sort(key=lambda item: item[2], reverse=True)

    # --- Dil tespiti ----------------------------------------------------------
    for row in kept:
        row.language = detector(row.comment) if detector else "tr"
        report.languages[row.language] = report.languages.get(row.language, 0) + 1

    # --- Doğrulama 1: kesin azalan zaman damgaları ---------------------------
    report.monotonic_ok = all(
        kept[i].timestamp > kept[i + 1].timestamp for i in range(len(kept) - 1)
    ) if len(kept) > 1 else True

    # --- Doğrulama 2: damga -> etiket geri dönüşü -----------------------------
    roundtrip_ok = True
    for row in kept:
        age = (anchor - row.timestamp).total_seconds()
        if label_for_age(age) != row.label:
            roundtrip_ok = False
            break
    report.roundtrip_ok = roundtrip_ok

    return kept, report


def write_output(rows: list[Row], destination: Path) -> None:
    # BOM YAZILMAZ. BOM kalırsa .NET tarafında başlık "﻿guestname" olur,
    # GuestName eşleşmez ve her satır "Misafir" olarak kaydedilir.
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(OUT_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.guest_name,
                    row.comment,
                    row.rating if row.rating is not None else 3,
                    # ISO 8601, saniye hassasiyeti, düz "Z".
                    # .NET: TryParse(InvariantCulture, AdjustToUniversal|AssumeUniversal)
                    row.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "Import",
                    row.language,
                ]
            )


def write_xlsx(rows: list[Row], destination: Path) -> bool:
    try:
        from openpyxl import Workbook  # type: ignore
    except ImportError:
        return False

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(OUT_COLUMNS)
    for row in rows:
        cells = [
            row.guest_name,
            row.comment,
            str(row.rating if row.rating is not None else 3),
            row.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Import",
            row.language,
        ]
        sheet.append(cells)
        # TÜM hücreler metin olmalı. Gerçek tarih hücresi ExcelDataReader'dan
        # DateTime olarak döner ve tr-TR altında "04.08.2026 03:14:22" olup
        # "Z" bilgisi kaybolur.
        for cell in sheet[sheet.max_row]:
            cell.number_format = "@"
    workbook.save(destination)
    return True


def render_report(report: FileReport, rows: list[Row]) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"Kaynak      : {report.path}")
    add(f"Çapa (UTC)  : {report.anchor.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    add("")
    add(f"Toplam satır          : {report.total}")
    add(f"  boş yorum           : {report.dropped_empty}")
    add(f"  10 karakterden kısa : {report.dropped_short}")
    add(f"  tekrar eden Yorum ID: {report.dropped_duplicate}")
    add(f"  tarihi çözülemeyen  : {len(report.unparseable)}")
    add(f"YAZILAN SATIR         : {report.kept}")
    add("")
    add(f"Puanı boş olup 3 atanan satır: {report.blank_rating}")
    add("")

    if rows:
        add(f"Tarih aralığı: {rows[-1].timestamp.strftime('%Y-%m-%d %H:%M')} "
            f"→ {rows[0].timestamp.strftime('%Y-%m-%d %H:%M')}")
        distinct_days = len({r.timestamp.date() for r in rows})
        add(f"Farklı gün sayısı: {distinct_days}")
        add("")

    add("Dil dağılımı:")
    for code, count in sorted(report.languages.items(), key=lambda kv: -kv[1]):
        add(f"  {code:6} {count}")
    add("")

    add("Kovalar (yeniden eskiye):")
    add(f"  {'etiket':<18} {'adet':>5}  {'en yeni':<16} {'en eski':<16}")
    for label, count, oldest, newest in report.buckets:
        add(f"  {label:<18} {count:>5}  {newest.strftime('%Y-%m-%d %H:%M'):<16} "
            f"{oldest.strftime('%Y-%m-%d %H:%M'):<16}")
    add("")

    if report.unparseable:
        add("Çözülemeyen tarih ifadeleri:")
        for item in report.unparseable[:20]:
            add(f"  {item}")
        if len(report.unparseable) > 20:
            add(f"  ... ve {len(report.unparseable) - 20} tane daha")
        add("")

    if report.order_breaks:
        add("UYARI — dosya sırası yeniden eskiye değil:")
        for item in report.order_breaks[:20]:
            add(f"  {item}")
        if len(report.order_breaks) > 20:
            add(f"  ... ve {len(report.order_breaks) - 20} tane daha")
        add("")

    add(f"DOĞRULAMA 1 (kesin azalan zaman damgası): {'PASS' if report.monotonic_ok else 'FAIL'}")
    add(f"DOĞRULAMA 2 (damga → etiket geri dönüşü): {'PASS' if report.roundtrip_ok else 'FAIL'}")

    return "\n".join(lines) + "\n"


def parse_anchor(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve()
    default_in = here.parents[2] / "reviews"

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-dir", type=Path, default=default_in)
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="varsayılan: <in-dir>/normalized")
    parser.add_argument("--anchor", type=str, default=None,
                        help="tüm dosyalar için çapa (ISO 8601). Varsayılan: dosyanın mtime'ı")
    parser.add_argument("--anchor-for", action="append", default=[],
                        metavar="AD=ISO8601", help="tek dosya için çapa")
    parser.add_argument("--no-spread", action="store_true",
                        help="her etiketi aralığın alt sınırına sabitle (kümelenmeyi geri getirir)")
    parser.add_argument("--emit-xlsx", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="dosya yazma, sadece raporla")
    args = parser.parse_args(argv)

    in_dir: Path = args.in_dir
    out_dir: Path = args.out_dir or (in_dir / "normalized")

    if not in_dir.is_dir():
        print(f"HATA: kaynak klasör yok: {in_dir}", file=sys.stderr)
        return 2

    global_anchor = parse_anchor(args.anchor) if args.anchor else None
    per_file_anchor: dict[str, datetime] = {}
    for item in args.anchor_for:
        if "=" not in item:
            print(f"HATA: --anchor-for biçimi AD=ISO8601 olmalı: {item}", file=sys.stderr)
            return 2
        name, _, value = item.partition("=")
        per_file_anchor[name.strip()] = parse_anchor(value.strip())

    detector = build_language_detector()
    if detector is None:
        print("UYARI: langdetect bulunamadı, tüm satırlara 'tr' yazılacak.", file=sys.stderr)

    sources = sorted(p for p in in_dir.glob("*.csv") if p.is_file())
    if not sources:
        print(f"HATA: {in_dir} altında .csv yok", file=sys.stderr)
        return 2

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    failures: list[str] = []
    grand_total = 0

    for source in sources:
        stem = source.stem
        anchor = (
            per_file_anchor.get(stem)
            or global_anchor
            or datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
        )
        if anchor > now:
            print(f"HATA: {stem} için çapa gelecekte: {anchor.isoformat()}", file=sys.stderr)
            return 2

        rows, report = normalize_file(source, anchor, spread=not args.no_spread, detector=detector)
        text = render_report(report, rows)

        print("=" * 72)
        print(text)

        if not (report.monotonic_ok and report.roundtrip_ok):
            failures.append(stem)
            print(f"!! {stem}: doğrulama düştü, dosya yazılmadı.\n", file=sys.stderr)
            continue

        grand_total += report.kept

        if args.dry_run:
            continue

        write_output(rows, out_dir / f"{stem}.csv")
        (out_dir / f"{stem}.report.txt").write_text(text, encoding="utf-8")

        if args.emit_xlsx and not write_xlsx(rows, out_dir / f"{stem}.xlsx"):
            print("UYARI: openpyxl yok, .xlsx üretilemedi.", file=sys.stderr)

    print("=" * 72)
    print(f"Toplam yazılacak satır: {grand_total}")
    if args.dry_run:
        print("(dry-run — hiçbir dosya yazılmadı)")
    else:
        print(f"Çıktı klasörü: {out_dir}")

    if failures:
        print(f"\nDOĞRULAMASI DÜŞEN DOSYALAR: {', '.join(failures)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
