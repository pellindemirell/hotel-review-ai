from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


DEFAULT_INPUTS = [
    Path(r"D:\KodYazılımStaj1\audit_outputs\manual_review_required.xlsx"),
    Path(r"D:\KodYazılımStaj1\audit_outputs\manual_review_top200.xlsx"),
]
DEFAULT_OUT_JSON = Path(r"D:\KodYazılımStaj1\audit_outputs\absa_hard_pattern_candidates.json")
DEFAULT_OUT_MD = Path(r"D:\KodYazılımStaj1\audit_outputs\absa_hard_pattern_candidates.md")

STOPWORDS = {
    "ve", "ile", "bir", "bu", "şu", "o", "de", "da", "çok", "cok", "gibi", "ama", "fakat", "ancak",
    "için", "icin", "göre", "gore", "kadar", "daha", "ise", "mi", "mı", "mu", "mü", "ya", "yada",
}


def _pick(columns: list[str], key: str) -> str | None:
    for c in columns:
        if key in c.lower():
            return c
    return None


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", text.lower())
    return [t for t in raw if len(t) >= 3 and t not in STOPWORDS]


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(0, max(0, len(tokens) - n + 1))]


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_excel(path)
    cols = [str(c) for c in df.columns]
    clause_col = _pick(cols, "clause")
    type_col = _pick(cols, "type") or _pick(cols, "hata")
    current_col = _pick(cols, "current")
    suggested_col = _pick(cols, "suggested")
    out = []
    for _, r in df.iterrows():
        clause = str(r.get(clause_col, "")).strip() if clause_col else ""
        if not clause:
            continue
        out.append(
            {
                "clause": clause,
                "error_type": str(r.get(type_col, "unknown")).strip() if type_col else "unknown",
                "current": str(r.get(current_col, "")).strip() if current_col else "",
                "suggested": str(r.get(suggested_col, "")).strip() if suggested_col else "",
            }
        )
    return out


def build_candidates(rows: list[dict], min_freq: int) -> dict:
    by_type_uni = defaultdict(Counter)
    by_type_bi = defaultdict(Counter)
    by_type_tri = defaultdict(Counter)
    transition_counter = Counter()

    for row in rows:
        et = row["error_type"] or "unknown"
        toks = _tokens(row["clause"])
        for t in toks:
            by_type_uni[et][t] += 1
        for bg in _ngrams(toks, 2):
            by_type_bi[et][bg] += 1
        for tg in _ngrams(toks, 3):
            by_type_tri[et][tg] += 1

        cur = row["current"][:120]
        sug = row["suggested"][:120]
        if cur or sug:
            transition_counter[f"{cur} => {sug}"] += 1

    error_type_patterns = {}
    for et in sorted(set(by_type_uni.keys()) | set(by_type_bi.keys()) | set(by_type_tri.keys())):
        error_type_patterns[et] = {
            "top_unigrams": [{"phrase": k, "count": v} for k, v in by_type_uni[et].most_common(40) if v >= min_freq],
            "top_bigrams": [{"phrase": k, "count": v} for k, v in by_type_bi[et].most_common(40) if v >= min_freq],
            "top_trigrams": [{"phrase": k, "count": v} for k, v in by_type_tri[et].most_common(30) if v >= min_freq],
        }

    return {
        "total_rows": len(rows),
        "distinct_error_types": sorted(error_type_patterns.keys()),
        "error_type_patterns": error_type_patterns,
        "top_transitions": [{"transition": k, "count": v} for k, v in transition_counter.most_common(50)],
    }


def write_markdown(data: dict, out_md: Path) -> None:
    lines = [
        "# ABSA Hard Pattern Candidates",
        "",
        f"- Toplam satır: `{data['total_rows']}`",
        f"- Hata türleri: `{', '.join(data['distinct_error_types'])}`",
        "",
    ]
    for et, block in data["error_type_patterns"].items():
        lines.append(f"## {et}")
        uni = block["top_unigrams"][:12]
        bi = block["top_bigrams"][:12]
        tri = block["top_trigrams"][:8]
        if uni:
            lines.append("- Unigram: " + ", ".join(f"`{x['phrase']}`({x['count']})" for x in uni))
        if bi:
            lines.append("- Bigram: " + ", ".join(f"`{x['phrase']}`({x['count']})" for x in bi))
        if tri:
            lines.append("- Trigram: " + ", ".join(f"`{x['phrase']}`({x['count']})" for x in tri))
        lines.append("")

    lines.append("## En Sık Geçişler")
    for tr in data["top_transitions"][:20]:
        lines.append(f"- `{tr['transition']}` : {tr['count']}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mine ABSA hard pattern candidates from manual review files.")
    p.add_argument("--input", action="append", default=[], help="Input Excel path(s). Repeatable.")
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    p.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    p.add_argument("--min-freq", type=int, default=2)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    paths = [Path(x) for x in args.input] if args.input else DEFAULT_INPUTS
    rows = []
    for p in paths:
        rows.extend(_load_rows(p))
    data = build_candidates(rows, min_freq=max(1, args.min_freq))
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(data, out_md)
    print(json.dumps({"rows": data["total_rows"], "error_types": data["distinct_error_types"], "out_json": str(out_json), "out_md": str(out_md)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
