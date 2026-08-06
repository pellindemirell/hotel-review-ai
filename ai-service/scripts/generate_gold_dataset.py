from __future__ import annotations

import csv
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.engine import HodipEngine

OUTPUT_DIR = Path(r"D:\KodYazılımStaj1\datasets\gold")
RAW_DIR = OUTPUT_DIR / "raw"
ANNOTATED_DIR = OUTPUT_DIR / "annotated"

ENGLISH_FAILURE_KEYWORDS = {
    "dirty": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "clean": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "stain": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "smell": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "mold": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "ac": ("klima_ariza", "hvac", "maintenance"),
    "air conditioning": ("klima_ariza", "hvac", "maintenance"),
    "heating": ("klima_ariza", "hvac", "maintenance"),
    "cold": ("yemek_soguk", "food_beverage", "food_beverage"),
    "warm": ("yemek_soguk", "food_beverage", "food_beverage"),
    "rude": ("personel_davranis", "staff_service", "front_desk"),
    "unfriendly": ("personel_davranis", "staff_service", "front_desk"),
    "slow": ("yavas_hizmet", "staff_service", "food_beverage"),
    "wait": ("yavas_hizmet", "staff_service", "food_beverage"),
    "noise": ("gurultu_sorunu", "noise", "maintenance"),
    "loud": ("gurultu_sorunu", "noise", "maintenance"),
    "noisy": ("gurultu_sorunu", "noise", "maintenance"),
    "broken": ("oda_sorunu", "room_condition", "maintenance"),
    "towel": ("havlu_talebi", "room_condition", "housekeeping"),
    "bathroom": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "shower": ("temizlik_sorunu", "cleanliness", "housekeeping"),
    "food": ("yiyecek_kalitesi", "food_beverage", "food_beverage"),
    "breakfast": ("yiyecek_kalitesi", "food_beverage", "food_beverage"),
    "cocktail": ("icecek_sorunu", "food_beverage", "food_beverage"),
    "drink": ("icecek_sorunu", "food_beverage", "food_beverage"),
    "pool": ("havuz_sorunu", "amenities", "beach_pool_services"),
    "beach": ("plaj_sorunu", "beach_pool", "beach_pool_services"),
    "wifi": ("wi-fi_sorunu", "amenities", "maintenance"),
    "internet": ("wi-fi_sorunu", "amenities", "maintenance"),
    "parking": ("otopark_sorunu", "amenities", "concierge"),
    "check-in": ("checkin_sorunu", "checkin_checkout", "front_desk"),
    "checkout": ("checkout_sorunu", "checkin_checkout", "front_desk"),
    "reception": ("personel_davranis", "staff_service", "front_desk"),
    "guest relation": ("personel_davranis", "staff_service", "guest_relations"),
    "location": ("diger", "location", "concierge"),
    "value": ("diger", "value", "management"),
    "price": ("diger", "value", "management"),
    "kids": ("diger", "kids_friendly", "animation"),
    "children": ("diger", "kids_friendly", "animation"),
    "entertainment": ("diger", "entertainment", "animation"),
    "show": ("diger", "entertainment", "animation"),
    "disco": ("diger", "entertainment", "animation"),
    "slide": ("diger", "amenities", "beach_pool_services"),
    "aqua": ("diger", "amenities", "beach_pool_services"),
    "spa": ("diger", "amenities", "beach_pool_services"),
}


def load_european_reviews(max_count: int = 10000) -> list[dict]:
    path = Path(r"D:\KodYazılımModelEğitimiVeri\european_reviews\Hotel_Reviews.csv")
    reviews = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            neg = (row.get("Negative_Review") or "").strip()
            pos = (row.get("Positive_Review") or "").strip()
            text_parts = []
            if pos and pos not in ("No Positive", "No positive"):
                text_parts.append(pos)
            if neg and neg not in ("No Negative", "No negative"):
                text_parts.append(neg)
            if not text_parts:
                continue
            reviews.append({
                "review_id": str(uuid.uuid4())[:8],
                "source": "booking",
                "language": "en",
                "hotel_name": row.get("Hotel_Name", ""),
                "review_text": ". ".join(text_parts),
                "review_rating": float(row.get("Reviewer_Score") or 0),
                "reviewer_nationality": row.get("Reviewer_Nationality", ""),
                "review_date": row.get("Review_Date", ""),
            })
            if len(reviews) >= max_count:
                break
    return reviews


def load_google_reviews() -> list[dict]:
    path = Path(r"D:\KodYazılımModelEğitimiVeri\crystal_waterworld_reviews_google_maps.csv")
    reviews = []
    if not path.exists():
        return reviews
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            if not text:
                text = (row.get("textTranslated") or "").strip()
            if not text:
                continue
            rating_str = (row.get("stars") or "").strip()
            rating = int(rating_str) if rating_str.isdigit() else 0
            reviews.append({
                "review_id": str(uuid.uuid4())[:8],
                "source": "google_maps",
                "language": row.get("originalLanguage") or row.get("language") or "en",
                "hotel_name": "Crystal Waterworld Resort & Spa",
                "review_text": text,
                "review_rating": rating,
                "reviewer_nationality": "",
                "review_date": row.get("publishedAtDate", ""),
            })
    return reviews


def split_into_clauses(text: str) -> list[str]:
    clauses = re.split(r"[.!?\n]+", text)
    return [c.strip() for c in clauses if len(c.strip()) > 10]


def keyword_match(clause: str) -> list[dict]:
    results = []
    clause_lower = clause.lower()
    for keyword, (failure_type, category, department) in ENGLISH_FAILURE_KEYWORDS.items():
        if keyword in clause_lower:
            results.append({
                "failure_type": failure_type,
                "category": category,
                "department": department,
                "keyword": keyword,
            })
    return results


def auto_annotate_en(review: dict) -> dict:
    text = review["review_text"]
    clauses = split_into_clauses(text)

    observations = []
    process_failures = []
    departments = []
    severity_list = []
    root_causes = []
    actions = []

    for i, clause_text in enumerate(clauses):
        clause_id = i + 1
        matches = keyword_match(clause_text)
        sentiment = "negative" if matches else "positive"

        for m in matches:
            obs_id = len(observations) + 1
            fail_id = len(process_failures) + 1

            observations.append({
                "observation_id": obs_id,
                "clause_id": clause_id,
                "fact": clause_text[:200],
                "category": m["category"],
            })
            process_failures.append({
                "failure_id": fail_id,
                "observation_id": obs_id,
                "failure_type": m["failure_type"],
                "description": clause_text[:200],
                "pattern_match": False,
            })
            departments.append({
                "department_id": len(departments) + 1,
                "failure_id": fail_id,
                "department": m["department"],
            })
            sev = 3 if m["failure_type"] in ("temizlik_sorunu", "personel_davranis") else 2
            severity_list.append({
                "severity_id": len(severity_list) + 1,
                "failure_id": fail_id,
                "guest_impact": sev,
                "business_impact": max(1, sev - 1),
                "urgency": sev,
            })
            root_causes.append({
                "root_cause_id": len(root_causes) + 1,
                "failure_id": fail_id,
                "cause_category": "quality_control",
                "cause_description": f"Keyword match: {m['keyword']}",
            })
            actions.append({
                "action_id": len(actions) + 1,
                "root_cause_id": len(root_causes),
                "action_type": "quality_audit",
                "description": f"Investigate {m['failure_type']} issue",
                "priority": "short_term" if sev < 4 else "immediate",
            })

    return {
        "review_id": review["review_id"],
        "source": review["source"],
        "language": review["language"],
        "hotel_name": review["hotel_name"],
        "review_text": text,
        "review_rating": review["review_rating"],
        "clauses": [{"clause_id": i + 1, "text": c, "sentiment": "negative" if keyword_match(c) else "positive", "start_char": 0, "end_char": 0} for i, c in enumerate(clauses)],
        "observations": observations,
        "process_failures": process_failures,
        "departments": departments,
        "sop": [],
        "severity": severity_list,
        "root_causes": root_causes,
        "actions": actions,
        "evidence": [],
        "annotator": "HODIP_auto_v1",
        "annotation_date": date.today().isoformat(),
        "annotation_notes": "Auto-annotated by keyword matching. Needs human review.",
    }


def auto_annotate_tr(review: dict, engine: HodipEngine) -> dict:
    result = engine.analyze(review["review_text"])
    clauses_raw = result.get("clauses", [])
    facts = result.get("facts", {})
    pfs = facts.get("process_failures", [])

    clauses = [{"clause_id": i + 1, "text": c, "sentiment": "neutral", "start_char": 0, "end_char": 0} for i, c in enumerate(clauses_raw)]
    observations = []
    process_failures = []
    departments = []
    severity_list = []
    root_causes = []
    actions = []

    for i, pf in enumerate(pfs):
        fail_id = i + 1
        obs_id = i + 1
        ft = getattr(pf, "failure_type", str(pf.get("type", "diger")))
        dept = getattr(pf, "department", pf.get("department", "other"))

        observations.append({
            "observation_id": obs_id,
            "clause_id": 1,
            "fact": str(pf)[:200],
            "category": "other",
        })
        process_failures.append({
            "failure_id": fail_id,
            "observation_id": obs_id,
            "failure_type": ft,
            "description": str(pf)[:200],
            "pattern_match": True,
        })
        departments.append({
            "department_id": len(departments) + 1,
            "failure_id": fail_id,
            "department": dept if isinstance(dept, str) else "other",
        })
        severity_list.append({
            "severity_id": len(severity_list) + 1,
            "failure_id": fail_id,
            "guest_impact": 3,
            "business_impact": 2,
            "urgency": 3,
        })
        root_causes.append({
            "root_cause_id": len(root_causes) + 1,
            "failure_id": fail_id,
            "cause_category": "process_design",
            "cause_description": str(pf)[:200],
        })
        actions.append({
            "action_id": len(actions) + 1,
            "root_cause_id": len(root_causes),
            "action_type": "process_change",
            "description": f"Address {ft}",
            "priority": "short_term",
        })

    return {
        "review_id": review["review_id"],
        "source": review["source"],
        "language": review["language"],
        "hotel_name": review["hotel_name"],
        "review_text": review["review_text"],
        "review_rating": review["review_rating"],
        "clauses": clauses,
        "observations": observations,
        "process_failures": process_failures,
        "departments": departments,
        "sop": [],
        "severity": severity_list,
        "root_causes": root_causes,
        "actions": actions,
        "evidence": [],
        "annotator": "HODIP_auto_v1",
        "annotation_date": date.today().isoformat(),
        "annotation_notes": "Auto-annotated by HODIP engine. Needs human review.",
    }


def main():
    print("=== HCOS Gold Dataset Generator v2 ===")
    print("Loading reviews...")

    european = load_european_reviews(5000)
    google = load_google_reviews()
    print(f"  European: {len(european)}")
    print(f"  Google Maps: {len(google)}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / "raw_reviews.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(european + google, f, ensure_ascii=False, indent=2)
    print(f"Saved raw: {raw_path}")

    engine = HodipEngine()

    annotated = []
    for i, review in enumerate(european):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(european)}")
        try:
            ann = auto_annotate_en(review)
            annotated.append(ann)
        except Exception as e:
            print(f"  Error on {i}: {e}")

    for i, review in enumerate(google):
        idx = len(european) + i + 1
        if (i + 1) % 200 == 0:
            print(f"  Google progress: {i + 1}/{len(google)}")
        try:
            lang = review.get("language", "en")
            if lang == "tr":
                ann = auto_annotate_tr(review, engine)
            else:
                ann = auto_annotate_en(review)
            annotated.append(ann)
        except Exception as e:
            print(f"  Error on google {i}: {e}")

    out_path = ANNOTATED_DIR / "annotated_batch_002.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(annotated, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")
    print(f"Total: {len(annotated)}")

    total_clauses = sum(len(a["clauses"]) for a in annotated)
    total_failures = sum(len(a["process_failures"]) for a in annotated)
    print(f"Clauses: {total_clauses}")
    print(f"Failures: {total_failures}")
    print(f"Avg: {total_clauses/len(annotated):.1f} clauses, {total_failures/len(annotated):.1f} failures/review")


if __name__ == "__main__":
    main()
