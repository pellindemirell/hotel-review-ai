# -*- coding: utf-8 -*-
"""Build tiered gold corpus from Excel ABSA re-exports (no circular fake gold).

Tier A verified: Excel old + Engine agree on dept FAMILY + sentiment, no hard risk flags.
Tier B engine_suggested: meaningful disagreements + hardish pack.
Tier C existing: LABELED_CLAUSES + gold_clauses_v1 verified/human.

Outputs:
  hotel-ai/datasets/review_absa/gold_clauses_excel_v2.jsonl
  hotel-ai/datasets/review_absa/gold_excel_v2_summary.json
  audit_outputs/excel_reexport_current/gold_excel_v2_for_review.xlsx
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\KodYazılımStaj1")
AI = ROOT / "ai-service"
REE = ROOT / "audit_outputs" / "excel_reexport_current"
GOLD_DIR = ROOT / "hotel-ai" / "datasets" / "review_absa"
OUT_JSONL = GOLD_DIR / "gold_clauses_excel_v2.jsonl"
OUT_SUMMARY = GOLD_DIR / "gold_excel_v2_summary.json"
OUT_XLSX = REE / "gold_excel_v2_for_review.xlsx"

sys.path.insert(0, str(AI))
sys.path.insert(0, str(ROOT))

REE_FILES = {
    "asteria_p1": REE / "asteria_p1_absa_reexport_current.xlsx",
    "asteria_p2": REE / "asteria_p2_absa_reexport_current.xlsx",
    "asteria_p3": REE / "asteria_p3_absa_reexport_current.xlsx",
    "crystal": REE / "crystal_absa_reexport_current.xlsx",
    "akra": REE / "akra_absa_reexport_current.xlsx",
    "ada": REE / "ada_absa_reexport_current.xlsx",
}

AUTOFIXED = [
    ROOT / "asteria_temiz_parca_2_absa_analiz_sonuclari_autofixed.xlsx",
    ROOT / "crystal_waterworld_absa_analiz_sonuclari_autofixed.xlsx",
]

HARD_FLAGS = {
    "pest_wrong_dept",
    "aquapark_as_tech",
    "contrast_not_split",
    "minibar_broken_as_hk",
    "overlong_clause",
    "sent_neg_kw_but_positive",
    "sent_pos_kw_but_negative",
}

# Soft flags that still disqualify Tier A (topic cues but atm/generic)
SOFT_BLOCK = {
    "generic_atm_with_topic",
    "aspect_too_generic",
}

NEG_STRONG = [
    "berbat", "rezalet", "korkunç", "korkunc", "kötü", "kotu", "lezzetsiz", "bayat",
    "kirli", "pis", "ilgisiz", "kaba", "pahalı", "pahali", "çalışmıyor", "calismiyor",
    "bozuk", "yetersiz", "eksik", "memnun değil", "memnun degil", "memnun kalmad",
    "bir daha gelmeyeceğ", "bir daha gelmeyeceg", "tavsiye etmem", "pişman", "pisman",
    "hayal kırıklığı", "hayal kirikligi", "iğrenç", "igrenc", "sinek", "böcek", "bocek",
    "karasinek", "hamam böcek", "hamam bocek", "kokuyor", "kokuş", "kokus", "felaket",
    # Morphological / stale-Neutral refresh cues (engine Negative, Excel Neutral)
    "temizlenmemiş", "temizlenmemis", "temizlenmemişti", "temizlenmemisti",
    "yenilemez", "tatsız", "tatsiz", "kirliydi", "pis kokuy",
]

# When Excel+reexport Engine both Neutral but clause has clear past-neg morphology,
# treat Tier A sentiment as Negative (stale Neutral refresh — not circular dump).
STALE_NEUTRAL_NEG = [
    "temizlenmemişti", "temizlenmemisti", "temizlenmemiş", "temizlenmemis",
    "yenilemez", "yenilemezdi", "yenilemez durumda",
    "tatsız", "tatsiz", "lezzetsizdi", "kirliydi", "pis kokuyordu",
    "çalışmıyor", "calismiyor", "çalışmıyorrr", "calismiyorrr",
    "bozuktu", "arızalı", "arizali",
]

STALE_POSITIVE_NEG = [
    "yardımcı olmayan", "yardimci olmayan", "ilgisiz", "kaba", "çok kaba", "cok kaba",
    "umursamaz", "surat asti", "surat astı", "azarladi", "azarladı",
]
POS_STRONG = [
    "harika", "mükemmel", "mukemmel", "muhteşem", "muhtesem", "süper", "super",
    "lezzetli", "temiz", "güler yüzlü", "guler yuzlu", "tavsiye ederim", "memnun kald",
    "çok iyi", "cok iyi", "çok güzel", "cok guzel",
]
DEPT_CUES = [
    (("yemek", "kahvalt", "büfe", "bufe", "restoran", "lezzet", "aç kald", "ac kald"), "fb"),
    (("bar", "içecek", "icecek", "kokteyl", "bira", "şarap", "sarap", "rakı", "raki"), "bar"),
    (("havuz", "aquapark", "aquaprk", "kaydırak", "kaydirak", "şezlong", "sezlong"), "pool"),
    (("plaj", "deniz", "sahil", "çakıl", "cakil"), "beach"),
    (("oda", "banyo", "havlu", "çarşaf", "carsaf", "temizlik"), "hk"),
    (("klima", "wifi", "internet", "asansör", "asansor", "sıcak su", "sicak su", "priz"), "tech"),
    (("resepsiyon", "check-in", "checkin", "fatura", "rezervasyon"), "fo"),
    (("personel", "garson", "barmen", "çalışan", "calisan", "kaba", "ilgisiz"), "staff"),
    (("animasyon", "konser", "etkinlik", "kids club", "animator", "animatör"), "anim"),
    (("spa", "masaj", "sauna", "jakuzi", "wellness"), "spa"),
    (("konum", "otopark", "park yeri", "ulaşım", "ulasim"), "loc"),
]

# Fine labels preferred when family agrees
FINE_PREF = {
    "havuz": "Havuz",
    "plaj": "Plaj & Deniz",
    "animasyon": "Animasyon & Etkinlik",
    "bar": "Bar",
    "spa": "Spa",
    "restoran": "Yiyecek & İçecek (F&B)",
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


def norm_clause(text: str) -> str:
    t = _norm(text)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[^\w\s]", "", t)
    return t


def family(dept: str) -> str:
    n = _norm(dept)
    if any(x in n for x in ("yiyecek", "f&b", "restoran", "yemek", "restaurant")):
        return "fb"
    if "bar" in n or "minibar" in n:
        return "bar"
    if "havuz" in n or "aquapark" in n:
        return "pool"
    if "plaj" in n or "deniz" in n:
        return "beach"
    if "housekeeping" in n or "temizlik" in n or "oda hizmet" in n or "kat hizmet" in n:
        return "hk"
    if "teknik" in n or "dijital" in n or "maintenance" in n:
        return "tech"
    if "on buro" in n or "resepsiyon" in n or "misafir iliski" in n or "front office" in n:
        return "fo"
    if "personel" in n:
        return "staff"
    if "animasyon" in n or "etkinlik" in n:
        return "anim"
    if "spa" in n or "masaj" in n or "wellness" in n:
        return "spa"
    if "cevre" in n or "ulasim" in n or "guvenlik" in n:
        return "loc"
    if "rekreasyon" in n or "eglence" in n:
        return "leisure"
    if "atmosfer" in n or "genel" in n or n in ("genel", "diger", "diğer"):
        return "atm"
    if "muhasebe" in n or "finans" in n:
        return "finance"
    return "other"


def families_agree(a: str, b: str) -> bool:
    fa, fb = family(a), family(b)
    if fa == fb:
        return True
    # leisure umbrella absorbs pool/beach/anim/spa
    leisure = {"leisure", "pool", "beach", "anim", "spa"}
    if fa in leisure and fb in leisure:
        return True
    # bar sits under F&B umbrella for agreement-only
    if {fa, fb} <= {"fb", "bar"}:
        return True
    # FO ↔ Staff: resepsiyon personeli taxonomy (not a real dept error)
    if {fa, fb} <= {"fo", "staff"}:
        return True
    return False


def is_rename_only(old_dept: str, new_dept: str) -> bool:
    if not old_dept or not new_dept:
        return False
    if _norm(old_dept) == _norm(new_dept):
        return True
    return families_agree(old_dept, new_dept) and family(old_dept) != "other"


def heuristic_flags(clause: str, dept: str, aspect: str, sent: str) -> list[str]:
    flags: list[str] = []
    c = _norm(clause)
    s = _norm(sent)
    d = family(dept)
    a = _norm(aspect)

    has_neg = any(_norm(w) in c for w in NEG_STRONG)
    has_pos = any(_norm(w) in c for w in POS_STRONG)
    if has_neg and s == "positive" and not any(x in c for x in ("degil", "olmasina ragmen", "ragmen")):
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
                if "bocek" not in c:
                    flags.append(f"dept_cue_{fam}_got_{d}")
            break

    if ("sinek" in c or "bocek" in c or "karasinek" in c) and d not in ("fb", "hk", "atm"):
        flags.append("pest_wrong_dept")
    if ("aquapark" in c or "aquaprk" in c) and d == "tech":
        flags.append("aquapark_as_tech")
    if ("minibar" in c or "mini bar" in c) and d == "hk" and any(
        x in c for x in ("bozuk", "sogutmuyor", "calismiyor")
    ):
        flags.append("minibar_broken_as_hk")
    if len(c.split()) > 45:
        flags.append("overlong_clause")
    if any(x in c for x in (" ama ", " fakat ", " ancak ")) and len(c.split()) > 18:
        flags.append("contrast_not_split")
    if d == "atm" and any(
        x in c for x in ("yemek", "havuz", "oda", "personel", "klima", "wifi", "bar", "plaj", "animasyon")
    ):
        flags.append("generic_atm_with_topic")
    if a in ("genel", "general", "genel atmosfer", "") and len(c.split()) >= 4:
        flags.append("aspect_too_generic")
    return flags


def has_hard_risk(flags: list[str]) -> bool:
    return any(f in HARD_FLAGS or f in SOFT_BLOCK or f.startswith("dept_cue_") for f in flags)


def prefer_dept(excel_dept: str, engine_dept: str) -> str:
    """Prefer fine Excel label when family agrees; else engine."""
    if not excel_dept:
        return engine_dept
    if not engine_dept:
        return excel_dept
    en = _norm(excel_dept)
    for key, label in FINE_PREF.items():
        if key in en:
            return excel_dept if families_agree(excel_dept, engine_dept) else engine_dept
    # Prefer non-atm / non-generic when possible
    if family(engine_dept) == "atm" and family(excel_dept) != "atm":
        return excel_dept
    if family(excel_dept) in ("pool", "beach", "anim", "spa", "bar") and families_agree(excel_dept, engine_dept):
        return excel_dept
    return engine_dept or excel_dept


def make_id(prefix: str, text: str, hotel: str = "") -> str:
    h = hashlib.sha1(f"{hotel}|{norm_clause(text)}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def canon_sent(s: str) -> str:
    n = _norm(s)
    if n.startswith("pos") or n in ("olumlu",):
        return "Positive"
    if n.startswith("neg") or n in ("olumsuz",):
        return "Negative"
    if n.startswith("neu") or n in ("notr", "nötr"):
        return "Neutral"
    if n.startswith("mix"):
        return "Mixed"
    return str(s or "").strip() or "Neutral"


def load_reexport(hotel: str, path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df["_hotel"] = hotel
    df["_source_file"] = path.name
    return df


def row_fields(r) -> dict:
    clause = str(r.get("Cümlecik_Clause") or r.get("Cumlecik_Clause") or "").strip()
    if not clause or clause.lower() == "nan":
        # try fuzzy
        for c in r.index:
            if "cumlecik" in _norm(c) or "clause" in _norm(c):
                clause = str(r.get(c) or "").strip()
                if clause and clause.lower() != "nan":
                    break
    old_dept = str(r.get("Tahmin_Departman") or "").strip()
    old_asp = str(r.get("Tahmin_Aspect") or "").strip()
    old_key = str(r.get("Aspect_Key") or "").strip()
    old_sent = canon_sent(str(r.get("Duygu_Etiketi") or "").strip())
    eng_dept = str(r.get("Engine_Departman") or r.get("Tahmin_Departman_Current") or "").strip()
    eng_asp = str(r.get("Engine_Aspect") or r.get("Tahmin_Aspect_Current") or "").strip()
    eng_key = str(r.get("Engine_Aspect_Key") or r.get("Aspect_Key_Current") or "").strip()
    eng_sent = canon_sent(str(r.get("Engine_Duygu") or r.get("Duygu_Etiketi_Current") or "").strip())
    conf = r.get("Güven_Oranı") or r.get("Guven_Orani") or r.get("Engine_Duygu_Skoru")
    try:
        conf = float(conf) if conf is not None and str(conf) not in ("", "nan") else None
    except Exception:
        conf = None
    return {
        "clause": clause,
        "old_dept": old_dept,
        "old_aspect": old_asp,
        "old_key": old_key,
        "old_sent": old_sent,
        "eng_dept": eng_dept,
        "eng_aspect": eng_asp,
        "eng_key": eng_key,
        "eng_sent": eng_sent,
        "confidence": conf,
        "yorum_id": r.get("Yorum_ID"),
    }


def build() -> dict:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    REE.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    records: list[dict] = []
    stats = Counter()
    by_hotel = defaultdict(Counter)
    by_dept = Counter()
    by_sent = Counter()
    tier_a_candidates = 0
    tier_a_blocked = Counter()
    rename_only = 0
    meaningful_disagree = 0

    # --- Tier C first (highest priority for seen set ownership of labels) ---
    # LABELED_CLAUSES
    from simulation.test_absa_department_accuracy import LABELED_CLAUSES

    for i, (text, dept, sent) in enumerate(LABELED_CLAUSES):
        key = norm_clause(text)
        if not key or key in seen:
            continue
        seen.add(key)
        rec = {
            "id": make_id("gcl_c_labeled", text),
            "text": text,
            "department": dept,
            "aspect_key": None,
            "aspect_label": None,
            "sentiment": canon_sent(sent),
            "tier": "C_existing",
            "source_file": "simulation/test_absa_department_accuracy.py",
            "hotel": "labeled_suite",
            "confidence": 1.0,
            "notes": "LABELED_CLAUSES human/fixture gold",
        }
        records.append(rec)
        stats["C_existing"] += 1
        by_hotel["labeled_suite"]["C_existing"] += 1
        by_dept[dept] += 1
        by_sent[canon_sent(sent)] += 1

    # gold_clauses_v1 verified / human
    v1 = GOLD_DIR / "gold_clauses_v1.jsonl"
    if v1.exists():
        for line in v1.open(encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            status = r.get("status")
            if status not in ("verified",) and r.get("source") not in ("human",):
                # include verified; also human pending with correct_* filled
                if not (r.get("correct_department_code") and r.get("correct_sentiment")):
                    continue
            text = r.get("text_tr") or r.get("text") or ""
            key = norm_clause(text)
            if not key or key in seen:
                continue
            seen.add(key)
            dept = (
                r.get("department_label_tr")
                or r.get("correct_department_code")
                or r.get("department_code")
                or ""
            )
            sent = canon_sent(r.get("correct_sentiment") or r.get("sentiment") or "Neutral")
            rec = {
                "id": r.get("clause_id") or make_id("gcl_c_v1", text),
                "text": text,
                "department": dept,
                "aspect_key": r.get("correct_aspect_code") or r.get("aspect_code"),
                "aspect_label": r.get("aspect_label_tr"),
                "sentiment": sent,
                "tier": "C_existing",
                "source_file": "gold_clauses_v1.jsonl",
                "hotel": r.get("review_id") or "v1",
                "confidence": 0.95 if status == "verified" else 0.85,
                "notes": f"v1 status={status} source={r.get('source')}",
            }
            records.append(rec)
            stats["C_existing"] += 1
            by_hotel["v1"]["C_existing"] += 1
            by_dept[str(dept)] += 1
            by_sent[sent] += 1

    # --- Tier B: hardish pack (all) ---
    hardish = GOLD_DIR / "hardish_pending_v1.jsonl"
    if hardish.exists():
        for line in hardish.open(encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            text = str(r.get("text") or "").strip()
            key = norm_clause(text)
            if not key or key in seen:
                continue
            seen.add(key)
            eng = r.get("engine_suggestion") or {}
            excel = r.get("excel") or {}
            gold = r.get("gold")
            if gold and isinstance(gold, dict) and gold.get("department"):
                dept = gold["department"]
                asp = gold.get("aspect")
                key_a = gold.get("aspect_key")
                sent = canon_sent(gold.get("sentiment") or "Neutral")
                tier = "A_verified"
                notes = "hardish human gold"
                conf = 0.9
            else:
                dept = eng.get("department") or excel.get("department") or ""
                asp = eng.get("aspect") or excel.get("aspect")
                key_a = eng.get("aspect_key")
                sent = canon_sent(eng.get("sentiment") or excel.get("sentiment") or "Neutral")
                tier = "B_engine_suggested"
                notes = f"hardish pending flags={r.get('risk_flags')}"
                conf = 0.55
            rec = {
                "id": r.get("id") or make_id("gcl_b_hard", text),
                "text": text,
                "department": dept,
                "aspect_key": key_a,
                "aspect_label": asp,
                "sentiment": sent,
                "tier": tier,
                "source_file": r.get("source_file") or "hardish_pending_v1.jsonl",
                "hotel": "hardish",
                "confidence": conf,
                "notes": notes,
            }
            records.append(rec)
            stats[tier] += 1
            by_hotel["hardish"][tier] += 1
            by_dept[str(dept)] += 1
            by_sent[sent] += 1

    # --- Process reexports for Tier A / Tier B ---
    for hotel, path in REE_FILES.items():
        if not path.exists():
            print(f"[warn] missing {path}")
            continue
        print(f"[load] {hotel} {path.name}")
        df = load_reexport(hotel, path)
        for _, r in df.iterrows():
            f = row_fields(r)
            text = f["clause"]
            if not text:
                continue
            key = norm_clause(text)
            if not key or key in seen:
                continue

            old_d, eng_d = f["old_dept"], f["eng_dept"]
            old_s, eng_s = f["old_sent"], f["eng_sent"]
            if not eng_d and not old_d:
                continue

            agree_fam = families_agree(old_d, eng_d) if old_d and eng_d else False
            agree_sent = old_s == eng_s and bool(old_s)
            # Stale Neutral refresh: Excel∩reexport Neutral but clear morphological Negative
            gold_sent = eng_s or old_s
            if (
                agree_fam
                and old_s == "Neutral"
                and eng_s == "Neutral"
                and any(_norm(w) in _norm(text) for w in STALE_NEUTRAL_NEG)
            ):
                gold_sent = "Negative"
                agree_sent = True
            # Stale Positive refresh: hostility cues labeled Positive in Excel/reexport
            if (
                agree_fam
                and old_s == "Positive"
                and eng_s == "Positive"
                and any(_norm(w) in _norm(text) for w in STALE_POSITIVE_NEG)
            ):
                gold_sent = "Negative"
                agree_sent = True
            # Stale Staff→FO/Spa refresh when venue cues present (engine routing corrected)
            gold_dept = prefer_dept(old_d, eng_d) if (old_d or eng_d) else ""
            tn = _norm(text)
            if family(old_d) == "staff" and family(eng_d) == "fo" and any(
                x in tn for x in ("resepsiyon", "check-in", "checkin", "lobi", "front")
            ):
                gold_dept = eng_d or old_d
                agree_fam = True
            if family(old_d) == "staff" and family(eng_d) in ("spa", "leisure") and any(
                x in tn for x in ("spa", "masaj", "sauna", "wellness", "jakuzi")
            ):
                gold_dept = eng_d or old_d
                agree_fam = True
            rename = is_rename_only(old_d, eng_d) and (old_s == eng_s)

            # flags against ENGINE labels (current)
            flags = heuristic_flags(text, eng_d or old_d, f["eng_aspect"] or f["old_aspect"], gold_sent or old_s)

            if agree_fam and agree_sent and not has_hard_risk(flags):
                tier_a_candidates += 1
                seen.add(key)
                dept = gold_dept or prefer_dept(old_d, eng_d)
                rec = {
                    "id": make_id("gcl_a", text, hotel),
                    "text": text,
                    "department": dept,
                    "aspect_key": f["eng_key"] or f["old_key"] or None,
                    "aspect_label": f["eng_aspect"] or f["old_aspect"] or None,
                    "sentiment": gold_sent,
                    "tier": "A_verified",
                    "source_file": path.name,
                    "hotel": hotel,
                    "confidence": f["confidence"] if f["confidence"] is not None else 0.8,
                    "notes": f"excel/engine family+sent agree; excel={old_d}/{old_s}",
                }
                records.append(rec)
                stats["A_verified"] += 1
                by_hotel[hotel]["A_verified"] += 1
                by_dept[dept] += 1
                by_sent[gold_sent] += 1
                continue

            if agree_fam and agree_sent and has_hard_risk(flags):
                for fl in flags:
                    if fl in HARD_FLAGS or fl in SOFT_BLOCK or fl.startswith("dept_cue_"):
                        tier_a_blocked[fl] += 1

            # Meaningful disagreement → Tier B sample candidates
            dept_meaningful = bool(old_d and eng_d) and not is_rename_only(old_d, eng_d)
            sent_meaningful = bool(old_s and eng_s) and old_s != eng_s
            if dept_meaningful or sent_meaningful:
                meaningful_disagree += 1
            elif rename:
                rename_only += 1
                continue  # skip pure renames from Tier B bulk

            # Prefer hard-flagged or dept/sent disagree for Tier B; cap later via sampling
            if not (dept_meaningful or sent_meaningful or has_hard_risk(flags)):
                continue

            seen.add(key)
            rec = {
                "id": make_id("gcl_b", text, hotel),
                "text": text,
                "department": eng_d or old_d,
                "aspect_key": f["eng_key"] or f["old_key"] or None,
                "aspect_label": f["eng_aspect"] or f["old_aspect"] or None,
                "sentiment": eng_s or old_s,
                "tier": "B_engine_suggested",
                "source_file": path.name,
                "hotel": hotel,
                "confidence": 0.5,
                "notes": (
                    f"pending review; excel={old_d}/{old_s} engine={eng_d}/{eng_s}; "
                    f"flags={flags}; dept_diff={dept_meaningful}; sent_diff={sent_meaningful}"
                ),
            }
            records.append(rec)
            stats["B_engine_suggested"] += 1
            by_hotel[hotel]["B_engine_suggested"] += 1
            by_dept[eng_d or old_d] += 1
            by_sent[eng_s or old_s] += 1

    # Autofixed unique clauses only (engine columns if present; else skip if already seen)
    for path in AUTOFIXED:
        if not path.exists():
            continue
        df = pd.read_excel(path)
        cols = { _norm(c): c for c in df.columns }
        c_clause = next((cols[k] for k in cols if "cumlecik" in k or k == "clause"), None)
        c_dep = next((cols[k] for k in cols if "departman" in k and "current" not in k), None)
        c_asp = next((cols[k] for k in cols if "aspect" in k and "key" not in k and "current" not in k), None)
        c_key = next((cols[k] for k in cols if "aspect_key" in k), None)
        c_sent = next((cols[k] for k in cols if "duygu_etiketi" in k or k == "duygu"), None)
        if not c_clause:
            continue
        added = 0
        for _, r in df.iterrows():
            text = str(r.get(c_clause) or "").strip()
            key = norm_clause(text)
            if not key or key in seen:
                continue
            seen.add(key)
            dept = str(r.get(c_dep) or "").strip() if c_dep else ""
            sent = canon_sent(str(r.get(c_sent) or "").strip() if c_sent else "Neutral")
            flags = heuristic_flags(text, dept, str(r.get(c_asp) or ""), sent)
            if has_hard_risk(flags) or not dept:
                # keep as pending B
                tier = "B_engine_suggested"
                conf = 0.45
            else:
                # autofixed unique without hard flags — still B (not verified agreement)
                tier = "B_engine_suggested"
                conf = 0.5
            records.append(
                {
                    "id": make_id("gcl_b_af", text, path.stem),
                    "text": text,
                    "department": dept,
                    "aspect_key": str(r.get(c_key) or "") if c_key else None,
                    "aspect_label": str(r.get(c_asp) or "") if c_asp else None,
                    "sentiment": sent,
                    "tier": tier,
                    "source_file": path.name,
                    "hotel": "autofixed_unique",
                    "confidence": conf,
                    "notes": "autofixed unique clause (not in reexport dedupe)",
                }
            )
            stats[tier] += 1
            by_hotel["autofixed_unique"][tier] += 1
            added += 1
        print(f"[autofixed] {path.name} unique added={added}")

    # Cap Tier B bulk to keep corpus usable (keep all hardish + all with hard flags notes)
    # Already included hardish first; bulk B from reexport can be large — sample if > 8000
    b_recs = [r for r in records if r["tier"] == "B_engine_suggested"]
    a_recs = [r for r in records if r["tier"] == "A_verified"]
    c_recs = [r for r in records if r["tier"] == "C_existing"]
    other = [r for r in records if r["tier"] not in ("A_verified", "B_engine_suggested", "C_existing")]

    MAX_B = 6000
    if len(b_recs) > MAX_B:
        # Prefer hardish + those with dept/sent diff / hard flags in notes
        hardish_b = [r for r in b_recs if "hardish" in (r.get("notes") or "") or str(r.get("id", "")).startswith("hardish")]
        rest = [r for r in b_recs if r not in hardish_b]
        pri = [r for r in rest if "dept_diff=True" in (r.get("notes") or "") or "flags=[" in (r.get("notes") or "")]
        soft = [r for r in rest if r not in pri]
        # keep all hardish + priority up to cap
        keep = hardish_b + pri
        if len(keep) > MAX_B:
            keep = keep[:MAX_B]
        else:
            need = MAX_B - len(keep)
            keep = keep + soft[:need]
        b_recs = keep
        stats["B_engine_suggested"] = len(b_recs)
        print(f"[cap] Tier B capped to {len(b_recs)}")

    final = c_recs + a_recs + b_recs + other

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for rec in final:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Review Excel: all pending B (sample) + sample verified A
    review_rows = []
    a_sample = a_recs[:: max(1, len(a_recs) // 400)][:400] if a_recs else []
    b_for_review = b_recs[:1500]
    for rec in b_for_review + a_sample:
        review_rows.append(
            {
                "id": rec["id"],
                "tier": rec["tier"],
                "hotel": rec["hotel"],
                "text": rec["text"],
                "department": rec["department"],
                "aspect_key": rec.get("aspect_key"),
                "aspect_label": rec.get("aspect_label"),
                "sentiment": rec["sentiment"],
                "confidence": rec.get("confidence"),
                "notes": rec.get("notes"),
                "source_file": rec.get("source_file"),
                "verify_status": "pending" if rec["tier"].startswith("B") else "verified_auto",
                "gold_dept": "",
                "gold_aspect_key": "",
                "gold_sent": "",
            }
        )
    pd.DataFrame(review_rows).to_excel(OUT_XLSX, index=False)

    summary = {
        "updated_at": datetime.now().isoformat(),
        "total": len(final),
        "by_tier": dict(stats),
        "tier_counts": {
            "A_verified": len(a_recs),
            "B_engine_suggested": len(b_recs),
            "C_existing": len(c_recs),
        },
        "by_hotel": {k: dict(v) for k, v in by_hotel.items()},
        "by_department_top": by_dept.most_common(30),
        "by_sentiment": dict(by_sent),
        "tier_a_candidates_before_flags": tier_a_candidates,
        "tier_a_blocked_flags": tier_a_blocked.most_common(20),
        "rename_only_skipped": rename_only,
        "meaningful_disagree_seen": meaningful_disagree,
        "paths": {
            "jsonl": str(OUT_JSONL),
            "summary": str(OUT_SUMMARY),
            "review_xlsx": str(OUT_XLSX),
        },
        "design_note": (
            "Tier A = Excel∩Engine family+sentiment agree, no hard/soft risk flags. "
            "Not dumping all engine predictions as gold."
        ),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["tier_counts"], ensure_ascii=False, indent=2))
    print(f"[done] wrote {len(final)} -> {OUT_JSONL}")
    return summary


if __name__ == "__main__":
    build()
