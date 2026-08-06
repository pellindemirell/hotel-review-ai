from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.absa_service import split_clauses_absa
from app.services.clause_pipeline import classify_clause, reload_pipeline_config


DEFAULT_INPUTS = [
    Path(r"D:\KodYazılımStaj1\asteria_temiz_parca_2_absa_analiz_sonuclari_autofixed.xlsx"),
    Path(r"D:\KodYazılımStaj1\crystal_waterworld_absa_analiz_sonuclari_autofixed.xlsx"),
]
DEFAULT_OUT_DIR = Path(r"D:\KodYazılımStaj1\audit_outputs\nightly_metrics")
DEFAULT_LONG_EVAL = Path(r"D:\KodYazılımStaj1\audit_outputs\long_nopunct_eval_set.jsonl")

GENERIC_DEPARTMENTS = {"genel", "diğer", "diger", "unknown", "none", ""}
GENERIC_ASPECT_KEYS = {"general", "other", "unknown", "none", ""}
CONTRASTIVE_MARKERS = (" ama ", " fakat ", " ancak ", " lakin ")
NEGATION_WORDS = (" değil", " degil", " yok", " olmad", " olamadi", " olamıyor")
HARD_NEGATIVE_HINTS = (
    "kötü", "kotu", "berbat", "rezalet", "kirli", "pis", "yetersiz", "lezzetsiz", "kalitesiz", "mağdur", "magdur"
)
PRICE_NEGATION_POSITIVE = ("pahalı değil", "pahali degil", "fahiş değil", "fahis degil")


@dataclass
class ReviewRow:
    source_file: str
    comment_id: str
    text: str


def _pick_col(columns: list[str], key: str) -> str | None:
    for col in columns:
        low = str(col).lower()
        if key in low:
            return col
    return None


def _load_unique_reviews(inputs: list[Path], max_reviews: int | None = None) -> list[ReviewRow]:
    reviews: list[ReviewRow] = []
    seen: set[tuple[str, str]] = set()
    for file_path in inputs:
        if not file_path.exists():
            continue
        df = pd.read_excel(file_path)
        columns = [str(c) for c in df.columns]
        id_col = _pick_col(columns, "yorum_id") or "Yorum_ID"
        text_col = _pick_col(columns, "tam_orijinal_yorum") or _pick_col(columns, "orijinal")
        if not text_col or id_col not in df.columns:
            continue

        sub = df[[id_col, text_col]].dropna()
        for _, row in sub.iterrows():
            cid = str(row[id_col]).strip()
            txt = str(row[text_col]).strip()
            if not txt:
                continue
            key = (file_path.name, cid)
            if key in seen:
                continue
            seen.add(key)
            reviews.append(ReviewRow(source_file=file_path.name, comment_id=cid, text=txt))
            if max_reviews and len(reviews) >= max_reviews:
                return reviews
    return reviews


def _is_long_nopunct(text: str) -> bool:
    t = text.strip()
    return len(t.split()) >= 30 and not re.search(r"[.!?;:]", t)


def _expected_sentiment_for_contrastive(clause: str) -> str | None:
    c = f" {clause.lower()} "
    if not any(m in c for m in CONTRASTIVE_MARKERS):
        return None

    for marker in CONTRASTIVE_MARKERS:
        if marker not in c:
            continue
        _, right = c.split(marker, 1)
        if any(w in c for w in PRICE_NEGATION_POSITIVE):
            return "Positive"
        if any(n in right for n in NEGATION_WORDS) and any(h in right for h in ("iyi", "guzel", "güzel", "servis", "yemek", "oda", "personel")):
            return "Negative"
        if any(h in right for h in HARD_NEGATIVE_HINTS):
            return "Negative"
    return None


def _safe_ratio(num: int, den: int) -> float:
    return round(num / den, 6) if den else 0.0


def _evaluate_long_nopunct_dataset(dataset_path: Path) -> dict:
    if not dataset_path.exists():
        return {"dataset_found": False}

    lines = dataset_path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return {"dataset_found": True, "total": 0}

    under_min = 0
    leading_frag = 0
    total_clauses = 0
    counts = []
    for item in rows:
        text = str(item.get("review_text", "")).strip()
        if not text:
            continue
        clauses = split_clauses_absa(text)
        cnum = len(clauses)
        counts.append(cnum)
        total_clauses += cnum
        expected_min = int(item.get("expected_min_clauses", max(2, len(text.split()) // 20)))
        if cnum < expected_min:
            under_min += 1
        if any(c.strip().lower().startswith(("ve ", "ama ", "fakat ", "ancak ")) for c in clauses):
            leading_frag += 1

    total = len(counts)
    return {
        "dataset_found": True,
        "total": total,
        "avg_clauses": round(mean(counts), 4) if total else 0.0,
        "under_min_clause_rate": _safe_ratio(under_min, total),
        "leading_conjunction_fragment_rate": _safe_ratio(leading_frag, total),
    }


def compute_metrics(reviews: list[ReviewRow], long_eval_path: Path) -> dict:
    reload_pipeline_config()

    total_reviews = len(reviews)
    total_clauses = 0
    generic_clause_count = 0
    contrastive_total = 0
    contrastive_errors = 0
    clauses_per_review: list[int] = []

    long_reviews = 0
    long_review_clause_counts: list[int] = []
    long_undersegmented = 0

    for idx, row in enumerate(reviews, start=1):
        if idx % 100 == 0:
            print(f"[nightly] processed reviews: {idx}/{total_reviews}")
        clauses = split_clauses_absa(row.text)
        cnum = len(clauses)
        clauses_per_review.append(cnum)
        total_clauses += cnum

        if _is_long_nopunct(row.text):
            long_reviews += 1
            long_review_clause_counts.append(cnum)
            expected_min = max(2, len(row.text.split()) // 20)
            if cnum < expected_min:
                long_undersegmented += 1

        for clause in clauses:
            decision = classify_clause(clause)
            dep = (decision.department_label or "").strip().lower()
            asp_key = (decision.aspect_key or "").strip().lower()
            asp_label = (decision.aspect_label or "").strip().lower()
            if dep in GENERIC_DEPARTMENTS or asp_key in GENERIC_ASPECT_KEYS or asp_label in GENERIC_DEPARTMENTS:
                generic_clause_count += 1

            expected = _expected_sentiment_for_contrastive(clause)
            if expected is not None:
                contrastive_total += 1
                if (decision.sentiment or "").lower() != expected.lower():
                    contrastive_errors += 1

    eval_metrics = _evaluate_long_nopunct_dataset(long_eval_path)
    metrics = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_review_count": total_reviews,
        "source_clause_count": total_clauses,
        "genel_or_generic_clause_ratio": _safe_ratio(generic_clause_count, total_clauses),
        "avg_clause_per_review": round(mean(clauses_per_review), 4) if clauses_per_review else 0.0,
        "contrastive_negation_error_rate": _safe_ratio(contrastive_errors, contrastive_total),
        "contrastive_negation_sample_size": contrastive_total,
        "long_nopunct_review_count": long_reviews,
        "long_nopunct_undersegmented_rate": _safe_ratio(long_undersegmented, long_reviews),
        "long_nopunct_avg_clause_per_review": round(mean(long_review_clause_counts), 4) if long_review_clause_counts else 0.0,
        "long_nopunct_eval_metrics": eval_metrics,
    }
    return metrics


def write_outputs(metrics: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    latest_json = out_dir / "latest_metrics.json"
    history_json = out_dir / "metrics_history.jsonl"
    snapshot_json = out_dir / f"metrics_{stamp}.json"
    summary_md = out_dir / "latest_metrics.md"

    latest_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    with history_json.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

    md = [
        "# Nightly ABSA Metrics",
        "",
        f"- Time (UTC): `{metrics['generated_at_utc']}`",
        f"- Source reviews: `{metrics['source_review_count']}`",
        f"- Source clauses: `{metrics['source_clause_count']}`",
        f"- Generic ratio (`Genel/Diğer`): `{metrics['genel_or_generic_clause_ratio']:.2%}`",
        f"- Avg clauses/review: `{metrics['avg_clause_per_review']:.3f}`",
        f"- Contrastive-negation error rate: `{metrics['contrastive_negation_error_rate']:.2%}` "
        f"(n={metrics['contrastive_negation_sample_size']})",
        f"- Long nopunct under-segmentation rate: `{metrics['long_nopunct_undersegmented_rate']:.2%}`",
        f"- Long nopunct avg clauses/review: `{metrics['long_nopunct_avg_clause_per_review']:.3f}`",
    ]
    eval_block = metrics.get("long_nopunct_eval_metrics", {})
    if eval_block.get("dataset_found"):
        md.extend(
            [
                "",
                "## Long Nopunct Mini Eval",
                f"- Total: `{eval_block.get('total', 0)}`",
                f"- Avg clauses: `{eval_block.get('avg_clauses', 0.0)}`",
                f"- Under-min rate: `{eval_block.get('under_min_clause_rate', 0.0):.2%}`",
                f"- Leading conjunction fragment rate: `{eval_block.get('leading_conjunction_fragment_rate', 0.0):.2%}`",
            ]
        )
    summary_md.write_text("\n".join(md) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightly ABSA quality metrics generator.")
    parser.add_argument("--input", action="append", default=[], help="Input Excel path(s). Repeatable.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument(
        "--long-eval-path",
        default=str(DEFAULT_LONG_EVAL),
        help="Long/nopunct mini eval JSONL path.",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=0,
        help="Process at most N unique reviews (0 = all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(p) for p in args.input] if args.input else DEFAULT_INPUTS
    max_reviews = args.max_reviews if args.max_reviews and args.max_reviews > 0 else None
    reviews = _load_unique_reviews(input_paths, max_reviews=max_reviews)
    metrics = compute_metrics(reviews, Path(args.long_eval_path))
    write_outputs(metrics, Path(args.out_dir))
    print("Nightly ABSA metrics generated.")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
