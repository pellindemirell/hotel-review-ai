from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_INPUTS = [
    Path(r"D:\KodYazılımStaj1\asteria_temiz_parca_2_absa_analiz_sonuclari_autofixed.xlsx"),
    Path(r"D:\KodYazılımStaj1\crystal_waterworld_absa_analiz_sonuclari_autofixed.xlsx"),
]
DEFAULT_OUT = Path(r"D:\KodYazılımStaj1\audit_outputs\long_nopunct_eval_set.jsonl")
DEFAULT_SUMMARY = Path(r"D:\KodYazılımStaj1\audit_outputs\long_nopunct_eval_set_summary.json")


def _pick_col(columns: list[str], key: str) -> str | None:
    for col in columns:
        low = str(col).lower()
        if key in low:
            return col
    return None


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_candidate(text: str, min_words: int) -> bool:
    t = text.strip()
    return len(t.split()) >= min_words and not re.search(r"[.!?;:]", t)


def _difficulty_score(text: str) -> float:
    t = text.lower()
    words = t.split()
    conjunction_count = sum(t.count(w) for w in (" ve ", " ama ", " fakat ", " ancak ", " lakin ", " ayrıca ", " bir de "))
    keyword_count = sum(t.count(w) for w in ("değil", "degil", "yok", "kötü", "kotu", "berbat", "harika", "mükemmel", "mukemmel"))
    return len(words) + (conjunction_count * 6) + (keyword_count * 3)


def _expected_min_clauses(text: str) -> int:
    wc = len(text.split())
    base = max(2, wc // 20)
    if any(x in text.lower() for x in (" ama ", " fakat ", " ancak ", " lakin ")):
        base += 1
    return min(base, 8)


def _extract_candidates(files: list[Path], min_words: int) -> list[dict]:
    out: list[dict] = []
    for file_path in files:
        if not file_path.exists():
            continue
        df = pd.read_excel(file_path)
        columns = [str(c) for c in df.columns]
        id_col = _pick_col(columns, "yorum_id") or "Yorum_ID"
        text_col = _pick_col(columns, "tam_orijinal_yorum") or _pick_col(columns, "orijinal")
        if not text_col or id_col not in df.columns:
            continue
        sub = df[[id_col, text_col]].dropna().drop_duplicates(subset=[id_col, text_col])
        for _, row in sub.iterrows():
            text = str(row[text_col]).strip()
            if not _is_candidate(text, min_words):
                continue
            t_low = text.lower()
            conj_count = sum(t_low.count(w) for w in (" ve ", " ama ", " fakat ", " ancak ", " lakin ", " ayrıca ", " bir de "))
            out.append(
                {
                    "review_text": text,
                    "source_file": file_path.name,
                    "source_comment_id": str(row[id_col]),
                    "word_count": len(text.split()),
                    "conjunction_count": conj_count,
                    "contains_contrastive": any(x in t_low for x in (" ama ", " fakat ", " ancak ", " lakin ")),
                    "expected_min_clauses": _expected_min_clauses(text),
                    "difficulty_score": _difficulty_score(text),
                }
            )
    return out


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build long/no-punctuation ABSA mini eval set.")
    parser.add_argument("--input", action="append", default=[], help="Input Excel path(s). Repeatable.")
    parser.add_argument("--output", default=str(DEFAULT_OUT), help="Output JSONL path.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="Summary JSON path.")
    parser.add_argument("--min-words", type=int, default=30, help="Minimum word count for candidates.")
    parser.add_argument("--add-count", type=int, default=200, help="Number of new hard samples to add.")
    parser.add_argument("--max-total", type=int, default=1000, help="Maximum total dataset size.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(p) for p in args.input] if args.input else DEFAULT_INPUTS
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    existing = _load_existing(output_path)
    existing_by_key = {_normalize_key(str(r.get("review_text", ""))): r for r in existing}

    candidates = _extract_candidates(input_paths, args.min_words)
    candidates.sort(key=lambda r: r["difficulty_score"], reverse=True)

    added = 0
    for row in candidates:
        key = _normalize_key(row["review_text"])
        if key in existing_by_key:
            continue
        existing_by_key[key] = row
        added += 1
        if added >= args.add_count:
            break

    merged = list(existing_by_key.values())
    merged.sort(key=lambda r: r.get("difficulty_score", 0), reverse=True)
    merged = merged[: args.max_total]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(merged, start=1):
            row["sample_id"] = f"lnp_{idx:05d}"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_path": str(output_path),
        "total_samples": len(merged),
        "added_this_run": added,
        "min_words": args.min_words,
        "max_total": args.max_total,
        "avg_word_count": round(sum(r.get("word_count", 0) for r in merged) / len(merged), 2) if merged else 0.0,
        "contrastive_ratio": round(
            sum(1 for r in merged if r.get("contains_contrastive")) / len(merged), 4
        )
        if merged
        else 0.0,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Long/no-punctuation mini eval set updated.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
