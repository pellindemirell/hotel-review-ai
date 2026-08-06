"""
Tüm Excel ABSA çıktılarını güncel motorla karşılaştırır.

1) Hızlı sezgisel bayraklar (pandas) — tüm satırlar
2) Öncelikli örneklerde classify_clause yeniden tahmin
3) Hâlâ sorunlu kümeleri raporlar

Kullanım:
  python ai-service/scripts/audit_all_excel_post_fix.py
  set ABSA_AUDIT_SAMPLE=800 && python ai-service/scripts/audit_all_excel_post_fix.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\KodYazılımStaj1")
AI = ROOT / "ai-service"
OUT = ROOT / "audit_outputs" / "excel_post_fix_audit"
sys.path.insert(0, str(AI))

# Prefer originals (not autofixed duplicates); include all hotels user listed.
FILES = [
    ROOT / "asteria_temiz_parca_1_absa_analiz_sonuclari.xlsx",
    ROOT / "asteria_temiz_parca_2_absa_analiz_sonuclari.xlsx",
    ROOT / "asteria_temiz_parca_3_absa_analiz_sonuclari.xlsx",
    ROOT / "crystal_waterworld_absa_analiz_sonuclari.xlsx",
    ROOT / "akra_hotel_absa_analiz_sonuclari.xlsx",
    ROOT / "ada_hotel_absa_analiz_sonuclari.xlsx",
    # Autofixed — ayrı izlenir (eski düzeltme katmanı)
    ROOT / "asteria_temiz_parca_2_absa_analiz_sonuclari_autofixed.xlsx",
    ROOT / "crystal_waterworld_absa_analiz_sonuclari_autofixed.xlsx",
]

NEG_STRONG = [
    "berbat", "rezalet", "korkunç", "korkunc", "kötü", "kotu", "lezzetsiz", "bayat",
    "kirli", "pis", "ilgisiz", "kaba", "pahalı", "pahali", "çalışmıyor", "calismiyor",
    "bozuk", "yetersiz", "eksik", "memnun değil", "memnun degil", "memnun kalmad",
    "bir daha gelmeyeceğ", "bir daha gelmeyeceg", "tavsiye etmem", "pişman", "pisman",
    "hayal kırıklığı", "hayal kirikligi", "iğrenç", "igrenc", "sinek", "böcek", "bocek",
    "karasinek", "hamam böcek", "hamam bocek", "kokuyor", "kokuş", "kokus",
]
POS_STRONG = [
    "harika", "mükemmel", "mukemmel", "muhteşem", "muhtesem", "süper", "super",
    "lezzetli", "temiz", "güler yüzlü", "guler yuzlu", "tavsiye ederim", "memnun kald",
    "çok iyi", "cok iyi", "çok güzel", "cok guzel",
]
# Dept keyword → expected department family (normalized contains)
DEPT_CUES = [
    (("yemek", "kahvalt", "büfe", "bufe", "restoran", "lezzet", "aç kald", "ac kald"), "fb"),
    (("bar", "içecek", "icecek", "kokteyl", "bira", "şarap", "sarap", "rakı", "raki"), "bar"),
    (("havuz", "aquapark", "aquaprk", "kaydırak", "kaydirak", "şezlong", "sezlong"), "pool"),
    (("plaj", "deniz", "sahil", "çakıl", "cakil"), "beach"),
    (("oda", "banyo", "havlu", "çarşaf", "carsaf", "temizlik"), "hk"),
    (("klima", "wifi", "internet", "asansör", "asansor", "sıcak su", "sicak su"), "tech"),
    (("resepsiyon", "check-in", "checkin", "fatura", "rezervasyon"), "fo"),
    (("personel", "garson", "barmen", "çalışan", "calisan", "kaba", "ilgisiz"), "staff"),
    (("animasyon", "konser", "etkinlik", "kids club", "animator", "animatör"), "anim"),
    (("spa", "masaj", "sauna", "jakuzi", "wellness"), "spa"),
    (("konum", "otopark", "park yeri", "ulaşım", "ulasim"), "loc"),
]


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


def pick(cols, *keys: str) -> str | None:
    low = {c: _norm(c) for c in cols}
    for k in keys:
        kn = _norm(k)
        for c, cn in low.items():
            if kn in cn:
                return c
    return None


def family(dept: str) -> str:
    n = _norm(dept)
    if any(x in n for x in ("yiyecek", "f&b", "restoran", "yemek")):
        return "fb"
    if "bar" in n:
        return "bar"
    if "havuz" in n or "aquapark" in n:
        return "pool"
    if "plaj" in n or "deniz" in n:
        return "beach"
    if "housekeeping" in n or "temizlik" in n or "oda hizmet" in n or "kat hizmet" in n:
        return "hk"
    if "teknik" in n or "dijital" in n:
        return "tech"
    if "on buro" in n or "resepsiyon" in n or "misafir iliski" in n or "misafir ili" in n:
        return "fo"
    if "personel" in n:
        return "staff"
    if "animasyon" in n or "etkinlik" in n or "cocuk" in n:
        return "anim"
    if "spa" in n or "masaj" in n:
        return "spa"
    if "cevre" in n or "ulasim" in n or "guvenlik" in n:
        return "loc"
    if "rekreasyon" in n or "eglence" in n:
        return "leisure"
    if "atmosfer" in n or "genel" in n:
        return "atm"
    return "other"


def heuristic_flags(clause: str, dept: str, aspect: str, sent: str) -> list[str]:
    flags: list[str] = []
    c = _norm(clause)
    s = _norm(sent)
    d = family(dept)
    a = _norm(aspect)

    has_neg = any(x in c for x in (_norm(w) for w in NEG_STRONG))
    has_pos = any(x in c for x in (_norm(w) for w in POS_STRONG))
    if has_neg and s == "positive" and not any(x in c for x in ("degil", "olmasina ragmen", "rağmen")):
        # negation of negative can be positive — keep simple
        if not re.search(r"(degil|değil).{0,12}(kotu|kirli|pis|pahali)", c):
            flags.append("sent_neg_kw_but_positive")
    if has_pos and s == "negative" and not has_neg and "ama" not in c and "fakat" not in c:
        flags.append("sent_pos_kw_but_negative")

    for cues, fam in DEPT_CUES:
        if any(_norm(w) in c for w in cues):
            if fam == "fb" and d not in ("fb", "bar", "atm", "other"):
                if not any(x in c for x in ("personel", "garson", "sira", "kuyruk")):
                    flags.append(f"dept_cue_{fam}_got_{d}")
            elif fam == "pool" and d not in ("pool", "beach", "leisure", "atm", "other", "spa"):
                flags.append(f"dept_cue_{fam}_got_{d}")
            elif fam == "tech" and d not in ("tech", "hk", "atm", "other"):
                flags.append(f"dept_cue_{fam}_got_{d}")
            elif fam == "anim" and d not in ("anim", "leisure", "staff", "atm", "other"):
                flags.append(f"dept_cue_{fam}_got_{d}")
            elif fam == "spa" and d not in ("spa", "leisure", "pool", "atm", "other"):
                # pest: hamam bocek should be fb
                if "bocek" not in c and "bocek" not in c:
                    flags.append(f"dept_cue_{fam}_got_{d}")
            break

    if ("sinek" in c or "bocek" in c or "karasinek" in c) and d not in ("fb", "hk", "atm"):
        flags.append("pest_wrong_dept")
    if ("aquapark" in c or "aquaprk" in c) and d == "tech":
        flags.append("aquapark_as_tech")
    if "minibar" in c or "mini bar" in c:
        if d == "hk" and any(x in c for x in ("bozuk", "sogutmuyor", "calismiyor")):
            flags.append("minibar_broken_as_hk")
    if len(c.split()) > 45:
        flags.append("overlong_clause")
    if any(x in c for x in (" ama ", " fakat ", " ancak ")) and len(c.split()) > 18:
        flags.append("contrast_not_split")
    if d == "atm" and any(
        x in c
        for x in ("yemek", "havuz", "oda", "personel", "klima", "wifi", "bar", "plaj")
    ):
        flags.append("generic_atm_with_topic")
    if a in ("genel", "general", "") and len(c.split()) >= 4:
        flags.append("aspect_too_generic")
    return flags


def load_frames() -> pd.DataFrame:
    rows = []
    for path in FILES:
        if not path.exists():
            continue
        df = pd.read_excel(path)
        cols = list(df.columns)
        c_clause = pick(cols, "cumlecik_clause", "cümlecik_clause", "clause")
        c_dep = pick(cols, "tahmin_departman", "departman")
        c_asp = pick(cols, "tahmin_aspect")
        c_key = pick(cols, "aspect_key")
        c_sent = pick(cols, "duygu_etiketi", "duygu")
        c_score = pick(cols, "duygu_skoru")
        c_id = pick(cols, "yorum_id")
        c_anom = pick(cols, "anomali_bayrak", "anomali")
        c_uyum = pick(cols, "bolunme_uyum_durumu", "bölünme_uyum")
        c_uyump = pick(cols, "bolunme_uyum_%", "bölünme_uyum_%")
        if not c_clause:
            continue
        for i, row in df.iterrows():
            clause = str(row.get(c_clause, "") or "").strip()
            if not clause or clause.lower() == "nan":
                continue
            rows.append(
                {
                    "source_file": path.name,
                    "is_autofixed": "autofixed" in path.name,
                    "excel_row": int(i) + 2,
                    "yorum_id": row.get(c_id) if c_id else None,
                    "clause": clause,
                    "old_dept": str(row.get(c_dep, "") or "").strip() if c_dep else "",
                    "old_aspect": str(row.get(c_asp, "") or "").strip() if c_asp else "",
                    "old_aspect_key": str(row.get(c_key, "") or "").strip() if c_key else "",
                    "old_sent": str(row.get(c_sent, "") or "").strip() if c_sent else "",
                    "old_score": row.get(c_score) if c_score else None,
                    "anomaly": str(row.get(c_anom, "") or "").strip() if c_anom else "",
                    "split_uyum": str(row.get(c_uyum, "") or "").strip() if c_uyum else "",
                    "split_uyum_pct": row.get(c_uyump) if c_uyump else None,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sample_n = int(os.environ.get("ABSA_AUDIT_SAMPLE", "1200"))
    print(f"[audit] loading excel files… sample={sample_n}")
    df = load_frames()
    print(f"[audit] loaded {len(df)} clauses from {df['source_file'].nunique()} files")

    # --- Phase 1: heuristics ---
    flag_lists = []
    for _, r in df.iterrows():
        flag_lists.append(heuristic_flags(r["clause"], r["old_dept"], r["old_aspect"], r["old_sent"]))
    df["flags"] = flag_lists
    df["flag_count"] = df["flags"].apply(len)
    df["flag_join"] = df["flags"].apply(lambda xs: "|".join(xs))

    originals = df[~df["is_autofixed"]].copy()
    flagged = originals[originals["flag_count"] > 0].copy()

    flag_counter: Counter = Counter()
    for xs in originals["flags"]:
        flag_counter.update(xs)

    per_file = (
        originals.groupby("source_file")
        .agg(rows=("clause", "count"), flagged=("flag_count", lambda s: int((s > 0).sum())))
        .reset_index()
    )
    per_file["flag_rate_pct"] = (100 * per_file["flagged"] / per_file["rows"]).round(2)

    # --- Phase 2: prioritize sample for reclassify ---
    # Priority: aquapark_as_tech, pest, sent mismatches, contrast, generic atm, anomaly text
    priority_order = [
        "aquapark_as_tech",
        "pest_wrong_dept",
        "sent_neg_kw_but_positive",
        "minibar_broken_as_hk",
        "contrast_not_split",
        "generic_atm_with_topic",
        "dept_cue_",
        "aspect_too_generic",
        "overlong_clause",
    ]

    def prio(flags: list[str]) -> int:
        score = 0
        for i, key in enumerate(priority_order):
            if any(f.startswith(key) or f == key for f in flags):
                score += (len(priority_order) - i) * 10
        return score + len(flags)

    originals["prio"] = originals["flags"].apply(prio)
    # always include anomaly-ish split fails
    originals.loc[
        originals["split_uyum"].str.contains("FARKLI|KISMEN|FAIL", case=False, na=False),
        "prio",
    ] += 15
    originals.loc[originals["anomaly"].astype(str).str.len() > 2, "prio"] += 8

    sample = originals.sort_values(["prio", "flag_count"], ascending=False).head(sample_n).copy()
    print(f"[audit] reclassifying sample={len(sample)} (flagged_all={len(flagged)})")

    from app.services.clause_pipeline import classify_clause, reload_pipeline_config
    from app.services.ontology_service import reload_ontology
    from app.services.turkish_nlp_utils import normalize_turkish

    reload_pipeline_config()
    reload_ontology()

    new_deps, new_asps, new_keys, new_sents, new_scores = [], [], [], [], []
    for i, (_, r) in enumerate(sample.iterrows(), 1):
        if i % 100 == 0:
            print(f"[audit] classify {i}/{len(sample)}")
        d = classify_clause(r["clause"])
        new_deps.append(d.department_label or "")
        new_asps.append(d.aspect_label or "")
        new_keys.append(getattr(d, "aspect_key", "") or "")
        new_sents.append(d.sentiment or "")
        new_scores.append(getattr(d, "sentiment_score", None))

    sample["new_dept"] = new_deps
    sample["new_aspect"] = new_asps
    sample["new_aspect_key"] = new_keys
    sample["new_sent"] = new_sents
    sample["new_score"] = new_scores
    sample["dept_changed"] = sample.apply(
        lambda r: bool(r["old_dept"] and r["new_dept"] and r["old_dept"] != r["new_dept"]), axis=1
    )
    sample["sent_changed"] = sample.apply(
        lambda r: bool(r["old_sent"] and r["new_sent"] and r["old_sent"].lower() != r["new_sent"].lower()),
        axis=1,
    )
    sample["aspect_changed"] = sample.apply(
        lambda r: bool(r["old_aspect"] and r["new_aspect"] and r["old_aspect"] != r["new_aspect"]),
        axis=1,
    )

    # Remaining risk: heuristic still fires on NEW prediction
    remain_flags = []
    for _, r in sample.iterrows():
        remain_flags.append(
            heuristic_flags(r["clause"], r["new_dept"], r["new_aspect"], r["new_sent"])
        )
    sample["new_flags"] = remain_flags
    sample["new_flag_count"] = sample["new_flags"].apply(len)
    sample["still_risky"] = sample["new_flag_count"] > 0
    sample["fixed_by_engine"] = (sample["flag_count"] > 0) & (sample["new_flag_count"] == 0)

    # Transition counters
    dept_trans = Counter()
    sent_trans = Counter()
    for _, r in sample.iterrows():
        if r["dept_changed"]:
            dept_trans[f"{r['old_dept']} => {r['new_dept']}"] += 1
        if r["sent_changed"]:
            sent_trans[f"{r['old_sent']} => {r['new_sent']}"] += 1

    remain_counter: Counter = Counter()
    for xs in sample.loc[sample["still_risky"], "new_flags"]:
        remain_counter.update(xs)

    # Export
    flagged.to_excel(OUT / "heuristic_flagged_all_originals.xlsx", index=False)
    sample.to_excel(OUT / "sample_reclassified.xlsx", index=False)
    sample[sample["still_risky"]].to_excel(OUT / "still_risky_after_engine.xlsx", index=False)
    sample[sample["fixed_by_engine"]].to_excel(OUT / "fixed_by_current_engine.xlsx", index=False)

    summary = {
        "updated_at": datetime.now().isoformat(),
        "total_clauses_all_files": int(len(df)),
        "total_original_clauses": int(len(originals)),
        "heuristic_flagged_originals": int(len(flagged)),
        "heuristic_flag_rate_pct": round(100 * len(flagged) / max(len(originals), 1), 2),
        "per_file": per_file.to_dict(orient="records"),
        "top_heuristic_flags": flag_counter.most_common(25),
        "sample_n": int(len(sample)),
        "sample_dept_changed": int(sample["dept_changed"].sum()),
        "sample_sent_changed": int(sample["sent_changed"].sum()),
        "sample_aspect_changed": int(sample["aspect_changed"].sum()),
        "sample_fixed_by_engine": int(sample["fixed_by_engine"].sum()),
        "sample_still_risky": int(sample["still_risky"].sum()),
        "top_dept_transitions": dept_trans.most_common(20),
        "top_sent_transitions": sent_trans.most_common(15),
        "top_remaining_risk_flags": remain_counter.most_common(20),
        "gold_note": "AbsaService gold LABELED_CLAUSES previously measured 221/221 dept+sent = 100%",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown report
    lines = [
        "# Excel ABSA Post-Fix Audit",
        "",
        f"- Updated: {summary['updated_at']}",
        f"- Original clauses: **{summary['total_original_clauses']}**",
        f"- Heuristic flagged: **{summary['heuristic_flagged_originals']}** ({summary['heuristic_flag_rate_pct']}%)",
        f"- Reclassified sample: **{summary['sample_n']}**",
        f"- Sample fixed by current engine (heuristic cleared): **{summary['sample_fixed_by_engine']}**",
        f"- Sample still risky after engine: **{summary['sample_still_risky']}**",
        "",
        "## Per file (originals)",
        "",
        "| File | Rows | Flagged | Rate |",
        "|---|---:|---:|---:|",
    ]
    for r in summary["per_file"]:
        lines.append(
            f"| {r['source_file']} | {r['rows']} | {r['flagged']} | {r['flag_rate_pct']}% |"
        )
    lines += ["", "## Top heuristic flags (Excel labels)", ""]
    for k, v in summary["top_heuristic_flags"]:
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Top remaining risk flags (after current engine)", ""]
    for k, v in summary["top_remaining_risk_flags"]:
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Top dept transitions (Excel → current)", ""]
    for k, v in summary["top_dept_transitions"]:
        lines.append(f"- {k}: {v}")
    lines += ["", "## Top sentiment transitions", ""]
    for k, v in summary["top_sent_transitions"]:
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## Artifacts",
        f"- `{OUT / 'heuristic_flagged_all_originals.xlsx'}`",
        f"- `{OUT / 'sample_reclassified.xlsx'}`",
        f"- `{OUT / 'still_risky_after_engine.xlsx'}`",
        f"- `{OUT / 'fixed_by_current_engine.xlsx'}`",
        f"- `{OUT / 'summary.json'}`",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "total_original_clauses", "heuristic_flagged_originals", "heuristic_flag_rate_pct",
        "sample_n", "sample_fixed_by_engine", "sample_still_risky",
        "top_remaining_risk_flags",
    )}, ensure_ascii=False, indent=2))
    print(f"[audit] wrote {OUT}")


if __name__ == "__main__":
    main()
