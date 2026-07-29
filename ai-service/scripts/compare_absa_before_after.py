from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import reload_ontology


INPUTS = [
    Path(r"D:\KodYazılımStaj1\asteria_temiz_parca_2_absa_analiz_sonuclari.xlsx"),
    Path(r"D:\KodYazılımStaj1\crystal_waterworld_absa_analiz_sonuclari.xlsx"),
]
OUT_DIR = Path(r"D:\KodYazılımStaj1\audit_outputs")


def pick(columns: list[str], key: str) -> str | None:
    key_low = key.lower()
    for c in columns:
        if key_low in c.lower():
            return c
    return None


def run_one(path: Path, max_rows: int = 0) -> dict:
    df = pd.read_excel(path)
    cols = [str(c) for c in df.columns]
    clause_col = pick(cols, "cümlecik_clause") or pick(cols, "cumlecik_clause") or pick(cols, "clause")
    dep_col = pick(cols, "tahmin_departman") or pick(cols, "departman")
    asp_col = pick(cols, "tahmin_aspect") or pick(cols, "aspect")
    sent_col = pick(cols, "duygu_etiketi") or pick(cols, "duygu")
    score_col = pick(cols, "duygu_skoru")
    if not clause_col:
        raise RuntimeError(f"Clause column not found in {path}")

    diff_rows = []
    dep_changes = 0
    asp_changes = 0
    sent_changes = 0
    total = 0
    for idx, row in df.iterrows():
        if max_rows and idx >= max_rows:
            break
        if idx and idx % 500 == 0:
            print(f"[compare] {path.name}: processed {idx} rows")
        clause = str(row.get(clause_col, "")).strip()
        if not clause:
            continue
        total += 1
        old_dep = str(row.get(dep_col, "")).strip() if dep_col else ""
        old_asp = str(row.get(asp_col, "")).strip() if asp_col else ""
        old_sent = str(row.get(sent_col, "")).strip() if sent_col else ""
        old_score = row.get(score_col, None) if score_col else None

        d = classify_clause(clause)
        new_dep = d.department_label or ""
        new_asp = d.aspect_label or ""
        new_sent = d.sentiment or ""
        new_score = d.sentiment_score

        changed = False
        if old_dep and new_dep and old_dep != new_dep:
            dep_changes += 1
            changed = True
        if old_asp and new_asp and old_asp != new_asp:
            asp_changes += 1
            changed = True
        if old_sent and new_sent and old_sent.lower() != new_sent.lower():
            sent_changes += 1
            changed = True

        if changed:
            diff_rows.append(
                {
                    "source_file": path.name,
                    "excel_row": idx + 2,
                    "clause": clause,
                    "old_departman": old_dep,
                    "new_departman": new_dep,
                    "old_aspect": old_asp,
                    "new_aspect": new_asp,
                    "old_duygu": old_sent,
                    "new_duygu": new_sent,
                    "old_duygu_skoru": old_score,
                    "new_duygu_skoru": new_score,
                }
            )

    out_xlsx = OUT_DIR / f"{path.stem}_before_after_diff.xlsx"
    if diff_rows:
        pd.DataFrame(diff_rows).to_excel(out_xlsx, index=False)

    return {
        "file": path.name,
        "total_clauses": total,
        "departman_changes": dep_changes,
        "aspect_changes": asp_changes,
        "duygu_changes": sent_changes,
        "any_change_rows": len(diff_rows),
        "diff_file": str(out_xlsx) if diff_rows else None,
    }


def main() -> None:
    max_rows = int(os.environ.get("ABSA_COMPARE_MAX_ROWS", "0"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reload_pipeline_config()
    reload_ontology()

    summaries = [run_one(p, max_rows=max_rows) for p in INPUTS if p.exists()]
    out_json = OUT_DIR / "before_after_summary.json"
    out_md = OUT_DIR / "before_after_summary.md"
    out_json.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# ABSA Before/After Summary", ""]
    for s in summaries:
        lines.extend(
            [
                f"## {s['file']}",
                f"- Toplam clause: `{s['total_clauses']}`",
                f"- Departman değişen: `{s['departman_changes']}`",
                f"- Aspect değişen: `{s['aspect_changes']}`",
                f"- Duygu değişen: `{s['duygu_changes']}`",
                f"- En az bir alanı değişen satır: `{s['any_change_rows']}`",
                f"- Diff dosyası: `{s['diff_file']}`",
                "",
            ]
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
