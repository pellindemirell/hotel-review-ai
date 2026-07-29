# -*- coding: utf-8 -*-
"""
1) Hardish gold paket
2) Tüm orijinal Excel satırlarını güncel motorla yeniden sınıflandır
3) Otel bazlı re-export + diff + özet

Kullanım:
  python ai-service/scripts/reexport_excel_absa_current.py
  set ABSA_REEEXPORT_WORKERS=6
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\KodYazılımStaj1")
AI = ROOT / "ai-service"
OUT = ROOT / "audit_outputs" / "excel_reexport_current"
GOLD_OUT = ROOT / "hotel-ai" / "datasets" / "review_absa"
AUDIT = ROOT / "audit_outputs" / "excel_post_fix_audit"

sys.path.insert(0, str(AI))

ORIGINAL_FILES = [
    ROOT / "asteria_temiz_parca_1_absa_analiz_sonuclari.xlsx",
    ROOT / "asteria_temiz_parca_2_absa_analiz_sonuclari.xlsx",
    ROOT / "asteria_temiz_parca_3_absa_analiz_sonuclari.xlsx",
    ROOT / "crystal_waterworld_absa_analiz_sonuclari.xlsx",
    ROOT / "akra_hotel_absa_analiz_sonuclari.xlsx",
    ROOT / "ada_hotel_absa_analiz_sonuclari.xlsx",
]

HOTEL_KEY = {
    "asteria_temiz_parca_1_absa_analiz_sonuclari.xlsx": "asteria_p1",
    "asteria_temiz_parca_2_absa_analiz_sonuclari.xlsx": "asteria_p2",
    "asteria_temiz_parca_3_absa_analiz_sonuclari.xlsx": "asteria_p3",
    "crystal_waterworld_absa_analiz_sonuclari.xlsx": "crystal",
    "akra_hotel_absa_analiz_sonuclari.xlsx": "akra",
    "ada_hotel_absa_analiz_sonuclari.xlsx": "ada",
}


def _norm(s: str) -> str:
    return (
        str(s or "")
        .lower()
        .replace("ı", "i")
        .replace("İ", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def pick(cols, *keys: str):
    low = {c: _norm(c) for c in cols}
    for k in keys:
        kn = _norm(k)
        for c, cn in low.items():
            if kn in cn:
                return c
    return None


def is_noise_flags(flags) -> bool:
    f = str(flags)
    return f in {
        "['generic_atm_with_topic']",
        "['aspect_too_generic']",
        "['generic_atm_with_topic', 'aspect_too_generic']",
        "['aspect_too_generic', 'generic_atm_with_topic']",
    }


def build_hardish_gold() -> dict:
    GOLD_OUT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    src = AUDIT / "still_risky_after_engine.xlsx"
    if not src.exists():
        raise FileNotFoundError(src)
    df = pd.read_excel(src)
    hard = df[~df["new_flags"].astype(str).map(is_noise_flags)].copy()
    hard = hard.reset_index(drop=True)

    # Gold pack columns for human verification
    pack_rows = []
    jsonl_rows = []
    for i, r in hard.iterrows():
        gid = f"hardish_{i+1:04d}"
        suggested_dept = str(r.get("new_dept") or "")
        suggested_sent = str(r.get("new_sent") or "")
        suggested_aspect = str(r.get("new_aspect") or "")
        suggested_key = str(r.get("new_aspect_key") or "")
        flags = str(r.get("new_flags") or "")
        pack_rows.append(
            {
                "gold_id": gid,
                "source_file": r.get("source_file"),
                "yorum_id": r.get("yorum_id"),
                "excel_row": r.get("excel_row"),
                "clause": r.get("clause"),
                "excel_dept": r.get("old_dept"),
                "excel_aspect": r.get("old_aspect"),
                "excel_sent": r.get("old_sent"),
                "engine_dept": suggested_dept,
                "engine_aspect": suggested_aspect,
                "engine_aspect_key": suggested_key,
                "engine_sent": suggested_sent,
                "risk_flags": flags,
                # Human fill:
                "gold_dept": "",
                "gold_aspect_key": "",
                "gold_sent": "",
                "verify_status": "pending",  # pending|agree_engine|agree_excel|corrected|skip
                "notes": "",
            }
        )
        jsonl_rows.append(
            {
                "id": gid,
                "text": r.get("clause"),
                "source_file": r.get("source_file"),
                "excel": {
                    "department": r.get("old_dept"),
                    "aspect": r.get("old_aspect"),
                    "sentiment": r.get("old_sent"),
                },
                "engine_suggestion": {
                    "department": suggested_dept,
                    "aspect": suggested_aspect,
                    "aspect_key": suggested_key,
                    "sentiment": suggested_sent,
                },
                "risk_flags": flags,
                "gold": None,
                "status": "pending",
            }
        )

    xlsx_path = OUT / "hardish_gold_pack_for_labeling.xlsx"
    jsonl_path = GOLD_OUT / "hardish_pending_v1.jsonl"
    pd.DataFrame(pack_rows).to_excel(xlsx_path, index=False)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in jsonl_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_file = hard["source_file"].value_counts().to_dict() if "source_file" in hard.columns else {}
    summary = {
        "n": int(len(hard)),
        "xlsx": str(xlsx_path),
        "jsonl": str(jsonl_path),
        "by_source_file": by_file,
        "updated_at": datetime.now().isoformat(),
    }
    (OUT / "hardish_gold_pack_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[gold] wrote {len(hard)} rows -> {xlsx_path}")
    print(f"[gold] wrote jsonl -> {jsonl_path}")
    return summary


_WORKER_READY = False


def _init_worker():
    global _WORKER_READY
    os.chdir(str(AI))
    if str(AI) not in sys.path:
        sys.path.insert(0, str(AI))
    from app.services.clause_pipeline import reload_pipeline_config
    from app.services.ontology_service import reload_ontology

    reload_pipeline_config()
    reload_ontology()
    _WORKER_READY = True


def _classify_one(clause: str) -> dict:
    from app.services.clause_pipeline import classify_clause

    d = classify_clause(clause)
    return {
        "new_dept": d.department_label or "",
        "new_aspect": d.aspect_label or "",
        "new_aspect_key": getattr(d, "aspect_key", "") or "",
        "new_sent": d.sentiment or "",
        "new_score": getattr(d, "sentiment_score", None),
    }


def classify_unique(clauses: list[str], workers: int) -> dict[str, dict]:
    uniq = sorted({c for c in clauses if c and c.lower() != "nan"})
    print(f"[reexport] unique clauses={len(uniq)} workers={workers}")
    out: dict[str, dict] = {}
    t0 = time.time()
    if workers <= 1:
        _init_worker()
        for i, c in enumerate(uniq, 1):
            out[c] = _classify_one(c)
            if i % 200 == 0:
                print(f"[reexport] classified {i}/{len(uniq)} elapsed={time.time()-t0:.0f}s")
        return out

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = {ex.submit(_classify_one, c): c for c in uniq}
        done = 0
        for fut in as_completed(futs):
            c = futs[fut]
            out[c] = fut.result()
            done += 1
            if done % 200 == 0:
                print(f"[reexport] classified {done}/{len(uniq)} elapsed={time.time()-t0:.0f}s")
    print(f"[reexport] classify done in {time.time()-t0:.1f}s")
    return out


def load_all_originals() -> pd.DataFrame:
    frames = []
    for path in ORIGINAL_FILES:
        if not path.exists():
            print(f"[warn] missing {path.name}")
            continue
        df = pd.read_excel(path)
        cols = list(df.columns)
        c_clause = pick(cols, "cumlecik_clause", "cümlecik_clause", "clause")
        if not c_clause:
            continue
        df = df.copy()
        df["_source_file"] = path.name
        df["_hotel"] = HOTEL_KEY.get(path.name, path.stem)
        df["_clause_col"] = c_clause
        frames.append(df)
        print(f"[load] {path.name}: {len(df)} rows")
    return frames


def reexport_all(workers: int = 4) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = load_all_originals()
    # Collect clauses
    all_clauses = []
    for df in frames:
        col = df["_clause_col"].iloc[0]
        all_clauses.extend(df[col].astype(str).str.strip().tolist())

    cache = classify_unique(all_clauses, workers=workers)

    hotel_summaries = []
    all_diff_rows = []
    total_rows = 0
    total_changed = 0

    for df in frames:
        source = df["_source_file"].iloc[0]
        hotel = df["_hotel"].iloc[0]
        cols = list(df.columns)
        c_clause = pick(cols, "cumlecik_clause", "cümlecik_clause", "clause")
        c_dep = pick(cols, "tahmin_departman", "departman")
        c_asp = pick(cols, "tahmin_aspect")
        c_key = pick(cols, "aspect_key")
        c_sent = pick(cols, "duygu_etiketi", "duygu")
        c_score = pick(cols, "duygu_skoru")
        c_id = pick(cols, "yorum_id")

        out_df = df.drop(columns=["_source_file", "_hotel", "_clause_col"], errors="ignore").copy()
        new_deps, new_asps, new_keys, new_sents, new_scores = [], [], [], [], []
        diff_local = []

        for idx, row in out_df.iterrows():
            clause = str(row.get(c_clause, "") or "").strip()
            pred = cache.get(clause) or {
                "new_dept": "",
                "new_aspect": "",
                "new_aspect_key": "",
                "new_sent": "",
                "new_score": None,
            }
            old_dep = str(row.get(c_dep, "") or "").strip() if c_dep else ""
            old_asp = str(row.get(c_asp, "") or "").strip() if c_asp else ""
            old_key = str(row.get(c_key, "") or "").strip() if c_key else ""
            old_sent = str(row.get(c_sent, "") or "").strip() if c_sent else ""
            old_score = row.get(c_score) if c_score else None

            new_deps.append(pred["new_dept"])
            new_asps.append(pred["new_aspect"])
            new_keys.append(pred["new_aspect_key"])
            new_sents.append(pred["new_sent"])
            new_scores.append(pred["new_score"])

            changed = (
                (old_dep and pred["new_dept"] and old_dep != pred["new_dept"])
                or (old_asp and pred["new_aspect"] and old_asp != pred["new_aspect"])
                or (old_sent and pred["new_sent"] and old_sent.lower() != pred["new_sent"].lower())
            )
            if changed:
                rec = {
                    "hotel": hotel,
                    "source_file": source,
                    "yorum_id": row.get(c_id) if c_id else None,
                    "excel_row": int(idx) + 2,
                    "clause": clause,
                    "old_dept": old_dep,
                    "new_dept": pred["new_dept"],
                    "old_aspect": old_asp,
                    "new_aspect": pred["new_aspect"],
                    "old_aspect_key": old_key,
                    "new_aspect_key": pred["new_aspect_key"],
                    "old_sent": old_sent,
                    "new_sent": pred["new_sent"],
                    "old_score": old_score,
                    "new_score": pred["new_score"],
                    "dept_changed": bool(old_dep and pred["new_dept"] and old_dep != pred["new_dept"]),
                    "aspect_changed": bool(old_asp and pred["new_aspect"] and old_asp != pred["new_aspect"]),
                    "sent_changed": bool(
                        old_sent and pred["new_sent"] and old_sent.lower() != pred["new_sent"].lower()
                    ),
                }
                diff_local.append(rec)
                all_diff_rows.append(rec)

        # Write re-export with both old and new columns for transparency
        out_df["Engine_Departman"] = new_deps
        out_df["Engine_Aspect"] = new_asps
        out_df["Engine_Aspect_Key"] = new_keys
        out_df["Engine_Duygu"] = new_sents
        out_df["Engine_Duygu_Skoru"] = new_scores
        # Also overwrite canonical prediction cols for a "current engine" view
        if c_dep:
            out_df["Tahmin_Departman_Current"] = new_deps
        if c_asp:
            out_df["Tahmin_Aspect_Current"] = new_asps
        if c_key:
            out_df["Aspect_Key_Current"] = new_keys
        if c_sent:
            out_df["Duygu_Etiketi_Current"] = new_sents
        if c_score:
            out_df["Duygu_Skoru_Current"] = new_scores

        reexport_path = OUT / f"{hotel}_absa_reexport_current.xlsx"
        out_df.to_excel(reexport_path, index=False)

        diff_path = OUT / f"{hotel}_before_after_diff.xlsx"
        if diff_local:
            pd.DataFrame(diff_local).to_excel(diff_path, index=False)

        dept_n = sum(1 for r in diff_local if r["dept_changed"])
        sent_n = sum(1 for r in diff_local if r["sent_changed"])
        asp_n = sum(1 for r in diff_local if r["aspect_changed"])
        total_rows += len(out_df)
        total_changed += len(diff_local)
        hotel_summaries.append(
            {
                "hotel": hotel,
                "source_file": source,
                "rows": int(len(out_df)),
                "any_change": int(len(diff_local)),
                "change_rate_pct": round(100 * len(diff_local) / max(len(out_df), 1), 2),
                "dept_changes": dept_n,
                "aspect_changes": asp_n,
                "sent_changes": sent_n,
                "reexport_file": str(reexport_path),
                "diff_file": str(diff_path) if diff_local else None,
            }
        )
        print(
            f"[hotel] {hotel}: rows={len(out_df)} changed={len(diff_local)} "
            f"dept={dept_n} sent={sent_n} asp={asp_n}"
        )

    if all_diff_rows:
        pd.DataFrame(all_diff_rows).to_excel(OUT / "ALL_hotels_before_after_diff.xlsx", index=False)

    # Top transitions
    dept_trans = Counter()
    sent_trans = Counter()
    for r in all_diff_rows:
        if r["dept_changed"]:
            dept_trans[f"{r['old_dept']} => {r['new_dept']}"] += 1
        if r["sent_changed"]:
            sent_trans[f"{r['old_sent']} => {r['new_sent']}"] += 1

    summary = {
        "updated_at": datetime.now().isoformat(),
        "total_rows": total_rows,
        "unique_clauses_classified": len(cache),
        "any_change_rows": total_changed,
        "change_rate_pct": round(100 * total_changed / max(total_rows, 1), 2),
        "hotels": hotel_summaries,
        "top_dept_transitions": dept_trans.most_common(25),
        "top_sent_transitions": sent_trans.most_common(15),
        "workers": workers,
    }
    (OUT / "reexport_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Excel Re-export Current Engine",
        "",
        f"- Updated: {summary['updated_at']}",
        f"- Total rows: **{summary['total_rows']}**",
        f"- Unique clauses classified: **{summary['unique_clauses_classified']}**",
        f"- Changed rows: **{summary['any_change_rows']}** ({summary['change_rate_pct']}%)",
        "",
        "## Per hotel",
        "",
        "| Hotel | Rows | Changed | Rate | Dept | Sent | Aspect |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for h in hotel_summaries:
        lines.append(
            f"| {h['hotel']} | {h['rows']} | {h['any_change']} | {h['change_rate_pct']}% | "
            f"{h['dept_changes']} | {h['sent_changes']} | {h['aspect_changes']} |"
        )
    lines += ["", "## Top dept transitions", ""]
    for k, v in summary["top_dept_transitions"]:
        lines.append(f"- {k}: {v}")
    lines += ["", "## Top sentiment transitions", ""]
    for k, v in summary["top_sent_transitions"]:
        lines.append(f"- {k}: {v}")
    lines += ["", f"Artifacts under `{OUT}`"]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("total_rows", "unique_clauses_classified", "any_change_rows", "change_rate_pct")}, ensure_ascii=False, indent=2))
    return summary


def main():
    workers = int(os.environ.get("ABSA_REEEXPORT_WORKERS", "4"))
    only = os.environ.get("ABSA_REEEXPORT_ONLY", "").strip().lower()
    if only in ("", "all", "both"):
        build_hardish_gold()
        reexport_all(workers=workers)
    elif only in ("gold", "hardish"):
        build_hardish_gold()
    elif only in ("reexport", "excel"):
        reexport_all(workers=workers)
    else:
        raise SystemExit(f"Unknown ABSA_REEEXPORT_ONLY={only}")


if __name__ == "__main__":
    main()
