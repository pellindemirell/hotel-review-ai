"""
HCOS ABSA Review Platform v2 — FastAPI Backend
Distributed review with auto-ABSA, corrections, audit trail
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .database import get_source_db, get_gold_db, push_to_gold, get_gold_stats, export_gold_for_training
from deep_translator import GoogleTranslator

# ---------------------------------------------------------------------------
# Chunked translate for long reviews
# ---------------------------------------------------------------------------

def translate_long_text(text: str, max_chunk: int = 4000) -> str:
    """Translate long text by splitting at sentence boundaries, max ~50K chars."""
    if not text:
        return ""
    text = text[:50000]
    if len(text) <= max_chunk:
        return GoogleTranslator(source="auto", target="tr").translate(text) or text
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) > max_chunk and current:
            chunks.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip() if current else s
    if current:
        chunks.append(current.strip())
    parts = []
    for chunk in chunks:
        try:
            parts.append(GoogleTranslator(source="auto", target="tr").translate(chunk[:4500]) or chunk[:4500])
        except Exception:
            parts.append(chunk)
    return " ".join(parts)


app = FastAPI(title="AI (Python) - HCOS ABSA Review Platform v2 (Etiketleme Platformu)", version="2.0.0")

# --- Auth helpers (simple token-based for stajyers) ---

def get_user_from_token(token: str) -> dict | None:
    """Stateless token lookup — survives server restarts."""
    username = STUDENT_TOKENS.get(token)
    if not username:
        return None
    from .database import get_source_db
    with get_source_db() as db:
        user = db.execute(
            "SELECT id, username, display_name, role FROM users WHERE username=? AND is_active=1",
            (username,),
        ).fetchone()
    return dict(user) if user else None

# Reverse department name normalization: short key -> full platform name
DEPT_NORMALIZE = {
    "genel": "Otel Atmosferi & Misafir Profili",
    "rooms": "Kat Hizmetleri & Temizlik",
    "housekeeping": "Kat Hizmetleri & Temizlik",
    "restaurant": "Yiyecek & İçecek",
    "bar": "Yiyecek & İçecek",
    "front_office": "Ön Büro & Misafir İlişkileri",
    "teknik": "Teknik Servis & IT",
    "havuz": "Rekreasyon & Eğlence",
    "spa": "Rekreasyon & Eğlence",
    "animasyon": "Rekreasyon & Eğlence",
    "personel": "Personel Davranışı",
    "diger": "Otel Atmosferi & Misafir Profili",
    "kat_hizmetleri": "Kat Hizmetleri & Temizlik",
    "otopark": "Çevre, Güvenlik & Ulaşım",
    "resepsiyon": "Ön Büro & Misafir İlişkileri",
    "spa_wellness": "Rekreasyon & Eğlence",
    "yiyecek_icecek": "Yiyecek & İçecek",
    "personel_davranis": "Personel Davranışı",
    "konum": "Çevre, Güvenlik & Ulaşım",
    "ulasim_servis": "Çevre, Güvenlik & Ulaşım",
    "guvenlik": "Çevre, Güvenlik & Ulaşım",
    "bahce": "Çevre, Güvenlik & Ulaşım",
    "kahvalti": "Yiyecek & İçecek",
    "yemek_kalitesi": "Yiyecek & İçecek",
    "restoran": "Yiyecek & İçecek",
    "servis_hizi": "Yiyecek & İçecek",
    "menu_cesitlilik": "Yiyecek & İçecek",
    "yiyecek": "Yiyecek & İçecek",
    "icecek": "Yiyecek & İçecek",
    "giris_cikis": "Ön Büro & Misafir İlişkileri",
    "rezervasyon": "Ön Büro & Misafir İlişkileri",
    "faturalandirma": "Ön Büro & Misafir İlişkileri",
    "danisma": "Ön Büro & Misafir İlişkileri",
    "oda_tahsis": "Ön Büro & Misafir İlişkileri",
    "oda_duzeni": "Kat Hizmetleri & Temizlik",
    "temizlik": "Kat Hizmetleri & Temizlik",
    "yatak": "Kat Hizmetleri & Temizlik",
    "banyo": "Kat Hizmetleri & Temizlik",
    "havlu": "Kat Hizmetleri & Temizlik",
    "oda_hizmetleri": "Kat Hizmetleri & Temizlik",
    "guler_yuz": "Personel Davranışı",
    "ilgi_alaka": "Personel Davranışı",
    "profesyonellik": "Personel Davranışı",
    "personel": "Personel Davranışı",
    "guest_experience": "Personel Davranışı",
    "havuz": "Rekreasyon & Eğlence",
    "spa": "Rekreasyon & Eğlence",
    "eglence_programi": "Rekreasyon & Eğlence",
    "cocuk_kulubu": "Rekreasyon & Eğlence",
    "plaj": "Rekreasyon & Eğlence",
    "spor_salonu": "Rekreasyon & Eğlence",
    "cevre_guvenlik": "Çevre, Güvenlik & Ulaşım",
    "otopark": "Çevre, Güvenlik & Ulaşım",
    "manzara": "Çevre, Güvenlik & Ulaşım",
    "ulasim": "Çevre, Güvenlik & Ulaşım",
    "iklimlendirme": "Teknik Servis & IT",
    "aydinlatma": "Teknik Servis & IT",
    "su_tesisati": "Teknik Servis & IT",
    "teknolojik_cihaz": "Teknik Servis & IT",
    "mobilya": "Teknik Servis & IT",
    "wifi": "Teknik Servis & IT",
    "dekor": "Otel Atmosferi & Misafir Profili",
    "konsept": "Otel Atmosferi & Misafir Profili",
    "ses_yalitimi": "Otel Atmosferi & Misafir Profili",
    "koku": "Otel Atmosferi & Misafir Profili",
    "aydinlatma_atmosfer": "Otel Atmosferi & Misafir Profili",
    "cevre": "Çevre, Güvenlik & Ulaşım",
}
# Also include full names mapping to themselves
for k, v in list(DEPT_NORMALIZE.items()):
    DEPT_NORMALIZE[v] = v


def norm_dept(d):
    if not d:
        return "Otel Atmosferi & Misafir Profili"
    return DEPT_NORMALIZE.get(d, d)

STUDENT_TOKENS = {
    "arda1": "arda1",
    "arda2": "arda2",
    "pelin": "pelin",
    "bahriye": "bahriye",
    "huseyin": "huseyin",
    "ozgur": "ozgur",
    "emre": "emre",
    "admin123": "admin",
}


def get_current_user(request: Request) -> dict:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return user


# --- Schemas ---


class LoginRequest(BaseModel):
    token: str


class AspectCorrect(BaseModel):
    text: str
    original_clause_text: str = ""
    is_new: bool = False
    aspect: str
    department: str = "Otel Atmosferi & Misafir Profili"
    sentiment: str = "NOTR"
    sentiment_score: float = 0.0
    priority: str = "ORTA"
    approved: bool = True
    context_wrong: bool = False
    context_correction: str = ""


class DepartmentCorrect(BaseModel):
    department: str
    approved: bool = True


class CorrectionSubmit(BaseModel):
    review_id: str
    aspects: list[AspectCorrect]
    departments: list[DepartmentCorrect]
    review_context: Optional[dict] = None


# --- Auth Endpoints ---


@app.post("/api/login")
def login(req: LoginRequest):
    user = get_user_from_token(req.token)
    if not user:
        raise HTTPException(401, "Geçersiz token veya kullanıcı aktif değil")
    return {"token": req.token, "user": user}


@app.get("/api/me")
def me(request: Request):
    return get_current_user(request)


# --- Review Queue ---


@app.get("/api/reviews/next")
def get_next_review(request: Request):
    user = get_current_user(request)

    with get_source_db() as db:
        # Get next pending review for this user
        row = db.execute(
            """SELECT r.id, r.review_text, r.review_text_translated,
                      r.language, r.rating, r.hotel_name, r.source
               FROM review_assignments ra
               JOIN reviews r ON r.id = ra.review_id
               WHERE ra.user_id=? AND ra.status='pending'
               ORDER BY CASE WHEN r.language IN ('tr','az','tk') THEN 0 ELSE 1 END, ra.assigned_at ASC
               LIMIT 1""",
            (user["id"],),
        ).fetchone()

        if not row:
            return {"status": "empty", "message": "Tüm yorumlar tamamlandı!"}

        review = dict(row)

        # in_progress'e al, aynı yorum tekrar gelmesin
        db.execute(
            "UPDATE review_assignments SET status='in_progress' WHERE review_id=? AND user_id=? AND status='pending'",
            (review["id"], user["id"]),
        )

        # Get auto-ABSA analysis
        absa = db.execute(
            """SELECT aspects_json, departments_json, clauses_json, failures_json
               FROM absa_auto WHERE review_id=?""",
            (review["id"],),
        ).fetchone()

        # Ceviri yoksa ve dil Turkce degilse, otomatik cevir (chunked)
        if not review.get("review_text_translated") and review.get("language","en") not in ("tr","az","tk"):
            try:
                translated = translate_long_text(review["review_text"] or "")
                if translated:
                    db.execute("UPDATE reviews SET review_text_translated=? WHERE id=?", (translated, review["id"]))
                    review["review_text_translated"] = translated
            except Exception:
                pass

        # Ceviri varsa her zaman Turkce metin uzerinden yeniden analiz et
        reanalyzed = False
        if review.get("review_text_translated"):
            from .absa_engine import analyze_batch
            new_result = analyze_batch(review["review_text_translated"])
            new_aspects = new_result.get("clauses", [])
            if new_aspects:
                db.execute(
                    "UPDATE absa_auto SET aspects_json=? WHERE review_id=?",
                    (json.dumps(new_aspects, ensure_ascii=False), review["id"]),
                )
                aspects = new_aspects
                reanalyzed = True
                departments_list = [{"department": d} for d in set(a.get("department", "diger") for a in new_aspects)]
                db.execute(
                    "UPDATE absa_auto SET departments_json=? WHERE review_id=?",
                    (json.dumps(departments_list, ensure_ascii=False), review["id"]),
                )

        # Normalize department names (handle legacy short keys)
        if not reanalyzed:
            aspects = json.loads(absa["aspects_json"]) if absa and absa["aspects_json"] else []
            for a in aspects:
                a["department"] = norm_dept(a.get("department", ""))
        else:
            for a in aspects:
                a["department"] = norm_dept(a.get("department", ""))

        # Çeviri varsa her clause için orijinal metni de ekle
        if review.get("review_text_translated"):
            from .absa_engine import split_clauses
            orig_clauses = split_clauses(review["review_text"])
            for i, asp in enumerate(aspects):
                if i < len(orig_clauses):
                    asp["original_text"] = orig_clauses[i][:250]
                else:
                    asp["original_text"] = ""

        # Her zaman 8 departmanin tümünü gönder, auto_detected flag ile
        ALL_DEPARTMENTS = [
            "Kat Hizmetleri & Temizlik",
            "Yiyecek & İçecek",
            "Ön Büro & Misafir İlişkileri",
            "Teknik Servis & IT",
            "Rekreasyon & Eğlence",
            "Çevre, Güvenlik & Ulaşım",
            "Otel Atmosferi & Misafir Profili",
            "Personel Davranışı",
        ]
        auto_depts = set(a.get("department") for a in aspects if a.get("department"))
        departments = [
            {"department": d, "auto_detected": d in auto_depts}
            for d in ALL_DEPARTMENTS
        ]

        # Load existing review context if any, otherwise set defaults
        raw_json = review.get("raw_json") or "{}"
        try:
            review_ctx = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except (json.JSONDecodeError, TypeError):
            review_ctx = {}
        review_context = {
            "yorum_turu": review_ctx.get("yorum_turu", ""),
            "musteri_profili": review_ctx.get("musteri_profili", ""),
            "konaklama_suresi": review_ctx.get("konaklama_suresi", ""),
            "one_cikan_kategori": review_ctx.get("one_cikan_kategori", ""),
        }

        # Compute summary
        scores = [a.get("sentiment_score", 0) for a in aspects]
        avg_score = sum(scores) / len(scores) if scores else 0
        summary = {
            "clause_count": len(aspects),
            "avg_sentiment": round(avg_score, 2),
            "overall_sentiment": "OLUMLU" if avg_score > 0.1 else "OLUMSUZ" if avg_score < -0.1 else "NOTR",
            "critical_count": sum(1 for a in aspects if a.get("priority") == "KRITIK"),
            "high_count": sum(1 for a in aspects if a.get("priority") == "YUKSEK"),
            "departments": list(set(a.get("department", "diger") for a in aspects)),
        }

        return {
            "status": "ok",
            "review": review,
            "auto_aspects": aspects,
            "auto_departments": departments,
            "summary": summary,
            "review_context": review_context,
        }


@app.get("/api/reviews/stats")
def get_stats(request: Request):
    user = get_current_user(request)
    with get_source_db() as db:
        total = db.execute(
            "SELECT COUNT(*) FROM review_assignments WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        done = db.execute(
            "SELECT COUNT(*) FROM review_assignments WHERE user_id=? AND status='completed'",
            (user["id"],),
        ).fetchone()[0]
        pending = db.execute(
            "SELECT COUNT(*) FROM review_assignments WHERE user_id=? AND status='pending'",
            (user["id"],),
        ).fetchone()[0]
        in_progress = db.execute(
            "SELECT COUNT(*) FROM review_assignments WHERE user_id=? AND status='in_progress'",
            (user["id"],),
        ).fetchone()[0]

    return {
        "total": total,
        "completed": done,
        "pending": pending,
        "in_progress": in_progress,
        "progress_pct": round(done / total * 100, 1) if total else 0,
    }


# --- Corrections ---


def run_incremental_training_flow(review_id: str, aspects: list[dict]):
    try:
        from collections import Counter
        from app.services.incremental_trainer import get_incremental_trainer
        from .database import get_source_db, get_gold_db
        import logging
        logger = logging.getLogger("ai_service")

        with get_source_db() as db:
            row = db.execute("SELECT review_text, rating FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not row:
            return
        review_text = row["review_text"]
        rating = row["rating"]

        if not aspects:
            return

        cats = [a["department"] for a in aspects if a.get("department")]
        sents = [a["sentiment"] for a in aspects if a.get("sentiment")]

        main_cat_platform = Counter(cats).most_common(1)[0][0] if cats else "Otel Atmosferi & Misafir Profili"
        main_sent_platform = Counter(sents).most_common(1)[0][0] if sents else "NOTR"

        PLATFORM_CAT_MAP = {
            "Kat Hizmetleri & Temizlik": "Kat Hizmetleri & Temizlik",
            "Yiyecek & İçecek": "Yiyecek & İçecek & Yemekler",
            "Ön Büro & Misafir İlişkileri": "Resepsiyon & Ön Büro",
            "Teknik Servis & IT": "Teknik Servis (Maintenance)",
            "Rekreasyon & Eğlence": "Spa & Wellness / Aktivite",
            "Çevre, Güvenlik & Ulaşım": "Çevre, Güvenlik & Ulaşım",
            "Personel Davranışı": "Personel Davranışı & İletişim",
            "Otel Atmosferi & Misafir Profili": "Diğer"
        }
        main_cat = PLATFORM_CAT_MAP.get(main_cat_platform, "Diğer")

        PLATFORM_SENT_MAP = {
            "OLUMLU": "Positive",
            "OLUMSUZ": "Negative",
            "NOTR": "Neutral"
        }
        main_sent = PLATFORM_SENT_MAP.get(main_sent_platform, "Neutral")

        from app.services.keyword_service import KeywordService
        keywords = KeywordService.extract_keywords(review_text)

        trainer = get_incremental_trainer()
        trainer.add_correction_sample(
            review_id=review_id,
            comment=review_text,
            correct_category=main_cat,
            correct_sentiment=main_sent,
            keywords=keywords,
            notes="Platform correction"
        )
        logger.info(f"Added correction sample for review {review_id} to incremental trainer.")

        with get_gold_db() as db:
            count = db.execute("SELECT COUNT(*) FROM gold_reviews").fetchone()[0]

        # Her 5 onaylı düzeltmede bir model ve RAG yeniden eğitilir/güncellenir
        if count > 0 and count % 5 == 0:
            logger.info("Triggering background retraining of category model and RAG index...")
            trainer.retrain_category_model(min_samples=5)
            trainer.update_rag_index()
            logger.info("Background retraining completed successfully.")

    except Exception as e:
        import logging
        logging.getLogger("ai_service").error(f"Incremental training error: {e}")


@app.post("/api/reviews/correct")
def submit_correction(req: CorrectionSubmit, request: Request, background_tasks: BackgroundTasks):
    user = get_current_user(request)

    with get_source_db() as db:
        # Verify assignment
        assignment = db.execute(
            """SELECT id, status FROM review_assignments
               WHERE review_id=? AND user_id=?""",
            (req.review_id, user["id"]),
        ).fetchone()

        if not assignment:
            raise HTTPException(403, "Bu yorum size atanmamış")

        # Collect new clauses to append to absa_auto
        new_clauses = []

        # Record each aspect correction
        aspects_approved = 0
        aspects_corrected = 0
        for asp in req.aspects:
            if asp.approved:
                aspects_approved += 1
            else:
                aspects_corrected += 1

            if asp.is_new:
                # Manually added clause — store as clause_add
                db.execute(
                    """INSERT INTO absa_corrections
                       (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        req.review_id,
                        user["id"],
                        "clause_add",
                        asp.aspect,
                        "",
                        json.dumps({"text": asp.text, "aspect": asp.aspect, "department": asp.department, "sentiment": asp.sentiment, "sentiment_score": asp.sentiment_score, "priority": asp.priority}, ensure_ascii=False),
                        "corrected",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                new_clauses.append({
                    "text": asp.text, "domain": "Turizm", "aspect": asp.aspect,
                    "department": asp.department, "sentiment_label": asp.sentiment,
                    "sentiment_score": asp.sentiment_score, "satisfaction": "Iyi",
                    "priority": asp.priority, "suggestion": "",
                    "confidence": 1.0, "original_text": "",
                })
            else:
                db.execute(
                    """INSERT INTO absa_corrections
                       (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        req.review_id,
                        user["id"],
                        "aspect",
                        asp.aspect,
                        asp.text,
                        asp.text,
                        "approved" if asp.approved else "corrected",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

            # Record context correction if applicable
            if asp.context_wrong and asp.context_correction:
                db.execute(
                    """INSERT INTO absa_corrections
                       (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        req.review_id,
                        user["id"],
                        "context",
                        "baglam",
                        asp.text,
                        asp.context_correction,
                        "corrected",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

            # Record clause text correction if user edited it
            if asp.original_clause_text and asp.text != asp.original_clause_text:
                db.execute(
                    """INSERT INTO absa_corrections
                       (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        req.review_id,
                        user["id"],
                        "clause_text",
                        f"clause_{asp.aspect}",
                        asp.original_clause_text[:500],
                        asp.text[:500],
                        "corrected",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

        # Record each department correction
        depts_approved = 0
        depts_corrected = 0
        for dept in req.departments:
            if dept.approved:
                depts_approved += 1
            else:
                depts_corrected += 1

            db.execute(
                """INSERT INTO absa_corrections
                   (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    req.review_id,
                    user["id"],
                    "department",
                    dept.department,
                    dept.department,
                    dept.department,
                    "approved" if dept.approved else "corrected",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        # Append new clauses to absa_auto
        if new_clauses:
            existing = db.execute("SELECT aspects_json FROM absa_auto WHERE review_id=?", (req.review_id,)).fetchone()
            if existing:
                try:
                    current = json.loads(existing["aspects_json"])
                except (json.JSONDecodeError, TypeError):
                    current = []
                current.extend(new_clauses)
                db.execute("UPDATE absa_auto SET aspects_json=? WHERE review_id=?", (json.dumps(current, ensure_ascii=False), req.review_id))

        # Save review-level context if provided
        if req.review_context:
            # Store in raw_json to avoid schema change
            existing_raw = db.execute("SELECT raw_json FROM reviews WHERE id=?", (req.review_id,)).fetchone()
            try:
                ctx = json.loads(existing_raw["raw_json"]) if existing_raw and existing_raw["raw_json"] else {}
            except (json.JSONDecodeError, TypeError):
                ctx = {}
            ctx.update(req.review_context)
            db.execute("UPDATE reviews SET raw_json=? WHERE id=?", (json.dumps(ctx, ensure_ascii=False), req.review_id))
            # Also log as correction records
            for key, val in req.review_context.items():
                if val:
                    db.execute(
                        """INSERT INTO absa_corrections
                           (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(uuid.uuid4()),
                            req.review_id,
                            user["id"],
                            "review_context",
                            key,
                            "",
                            str(val),
                            "corrected",
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )

        # Mark assignment as completed
        db.execute(
            "UPDATE review_assignments SET status='completed', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), assignment["id"]),
        )

    # Push approved data to gold DB
    approved_aspects = [
        {"text": a.text, "aspect": a.aspect, "department": a.department, "sentiment": a.sentiment,
         "sentiment_score": a.sentiment_score, "priority": a.priority,
         "context_wrong": a.context_wrong, "context_correction": a.context_correction}
        for a in req.aspects
    ]
    approved_depts = [
        {"department": d.department} for d in req.departments
    ]
    total = len(req.aspects) + len(req.departments)
    correct = aspects_approved + depts_approved
    quality = round(correct / total * 100, 1) if total else 100.0

    push_to_gold(
        review_id=req.review_id,
        aspects=approved_aspects,
        departments=approved_depts,
        reviewer_username=user["username"],
        quality_score=quality,
    )

    background_tasks.add_task(run_incremental_training_flow, req.review_id, approved_aspects)

    return {
        "status": "ok",
        "aspects_approved": aspects_approved,
        "aspects_corrected": aspects_corrected,
        "depts_approved": depts_approved,
        "depts_corrected": depts_corrected,
        "gold_db_updated": True,
    }


# --- Skip Review ---


@app.post("/api/reviews/skip")
def skip_review(request: Request):
    """Mevcut yorumu kuyrugun sonuna at ve logla."""
    user = get_current_user(request)
    with get_source_db() as db:
        # En son verilen in_progress yorumu bul
        cur = db.execute(
            """SELECT review_id FROM review_assignments
               WHERE user_id=? AND status='in_progress' LIMIT 1""",
            (user["id"],),
        ).fetchone()
        review_id = cur["review_id"] if cur else "unknown"

        # pending'e cevir, siralamada sona at
        db.execute(
            """UPDATE review_assignments
               SET status='pending', assigned_at=?
               WHERE user_id=? AND status='in_progress'""",
            (datetime.now(timezone.utc).isoformat(), user["id"]),
        )

        # Skip log'u kaydet
        db.execute(
            """INSERT INTO absa_corrections
               (id, review_id, user_id, field_type, field_name, original_value, corrected_value, action, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                review_id,
                user["id"],
                "skip",
                "yorum",
                "atlandi",
                "atlandi",
                "skipped",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return {"status": "ok"}


# --- Translate Endpoint ---


class TranslateRequest(BaseModel):
    review_id: str


@app.post("/api/reviews/translate")
def translate_review(req: TranslateRequest, request: Request):
    user = get_current_user(request)
    with get_source_db() as db:
        review = db.execute("SELECT * FROM reviews WHERE id=?", (req.review_id,)).fetchone()
    if not review:
        raise HTTPException(404, "Yorum bulunamadi")
    text = review["review_text"]
    if not text or len(text.strip()) < 3:
        raise HTTPException(400, "Cevrilecek metin yok")
    try:
        # Ceviriyi yap veya onbellekten al (chunked)
        translated = review["review_text_translated"]
        if not translated:
            translated = translate_long_text(text)
            with get_source_db() as db:
                db.execute("UPDATE reviews SET review_text_translated=? WHERE id=?", (translated, req.review_id))

        # Her zaman Turkce metin uzerinden yeniden ABSA analizi yap
        with get_source_db() as db:
            from .absa_engine import analyze_batch, split_clauses
            new_result = analyze_batch(translated)
            new_aspects = new_result.get("clauses", [])
            if new_aspects:
                db.execute(
                    "UPDATE absa_auto SET aspects_json=? WHERE review_id=?",
                    (json.dumps(new_aspects, ensure_ascii=False), req.review_id),
                )
                departments_list = [{"department": d} for d in set(a.get("department", "diger") for a in new_aspects)]
                db.execute(
                    "UPDATE absa_auto SET departments_json=? WHERE review_id=?",
                    (json.dumps(departments_list, ensure_ascii=False), req.review_id),
                )
                # Orijinal clause'lari da ekle
                orig_clauses = split_clauses(review["review_text"])
                for i, asp in enumerate(new_aspects):
                    asp["original_text"] = orig_clauses[i][:250] if i < len(orig_clauses) else ""
                aspects_json = json.dumps(new_aspects, ensure_ascii=False)
            else:
                aspects_json = "[]"
        return {"translated": translated, "cached": False, "aspects": json.loads(aspects_json)}
    except Exception as e:
        raise HTTPException(500, f"Ceviri hatasi: {e}")


# --- Admin Endpoints ---


@app.get("/api/admin/progress")
def admin_progress(request: Request):
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin yetkisi gerekli")

    with get_source_db() as db:
        # Per-user stats
        users = db.execute(
            """SELECT u.username, u.display_name,
                      COUNT(ra.id) as total,
                      SUM(CASE WHEN ra.status='completed' THEN 1 ELSE 0 END) as done,
                      SUM(CASE WHEN ra.status='pending' THEN 1 ELSE 0 END) as pending,
                      SUM(CASE WHEN ra.status='in_progress' THEN 1 ELSE 0 END) as in_progress,
                      (SELECT COUNT(*) FROM absa_corrections ac2 WHERE ac2.user_id = u.id AND ac2.action='skipped') as skipped
               FROM users u
               LEFT JOIN review_assignments ra ON ra.user_id = u.id
               WHERE u.role='reviewer'
               GROUP BY u.id
               ORDER BY u.display_name"""
        ).fetchall()

        # Global stats
        global_stats = db.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done
               FROM review_assignments"""
        ).fetchone()

        # Recent corrections (last 50)
        recent = db.execute(
            """SELECT ac.*, u.display_name as user_name, r.review_text
               FROM absa_corrections ac
               JOIN users u ON u.id = ac.user_id
               JOIN reviews r ON r.id = ac.review_id
               ORDER BY ac.created_at DESC
               LIMIT 50"""
        ).fetchall()

        # Accuracy stats
        corrections_by_type = db.execute(
            """SELECT field_type, action, COUNT(*) as count
               FROM absa_corrections GROUP BY field_type, action"""
        ).fetchall()

        accuracy = {}
        for row in corrections_by_type:
            ft = row["field_type"]
            if ft not in accuracy:
                accuracy[ft] = {"approved": 0, "corrected": 0, "total": 0}
            accuracy[ft][row["action"]] = row["count"]
            accuracy[ft]["total"] += row["count"]

        for ft in accuracy:
            a = accuracy[ft]
            a["accuracy_pct"] = round(a["approved"] / a["total"] * 100, 1) if a["total"] else 0

    return {
        "users": [dict(u) for u in users],
        "global": dict(global_stats),
        "recent_corrections": [dict(r) for r in recent],
        "accuracy_by_type": accuracy,
    }


@app.get("/api/admin/corrections/{username}")
def admin_user_corrections(username: str, request: Request, limit: int = 100):
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin yetkisi gerekli")

    with get_source_db() as db:
        rows = db.execute(
            """SELECT ac.*, u.display_name as user_name, r.review_text
               FROM absa_corrections ac
               JOIN users u ON u.id = ac.user_id
               JOIN reviews r ON r.id = ac.review_id
               WHERE u.username=?
               ORDER BY ac.created_at DESC
               LIMIT ?""",
            (username, limit),
        ).fetchall()

    return {"corrections": [dict(r) for r in rows]}


@app.get("/api/admin/reset-user/{username}")
def admin_reset_user(username: str, request: Request):
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin yetkisi gerekli")

    with get_source_db() as db:
        db.execute(
            """UPDATE review_assignments SET status='pending', completed_at=NULL
                WHERE user_id=(SELECT id FROM users WHERE username=?) AND status IN ('completed','in_progress')""",
            (username,),
        )
    return {"status": "ok", "message": f"{username} resetlendi"}


# --- Training data export ---


@app.get("/api/training/export")
def export_training_data(request: Request, limit: int = 0):
    """Gold DB'den egitim verisini disa aktar."""
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403)
    data = export_gold_for_training(limit)
    stats = get_gold_stats()
    return {"count": len(data), "gold_stats": stats, "data": data}


@app.get("/api/gold/stats")
def gold_stats(request: Request):
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403)
    return get_gold_stats()


# --- Serve Frontend ---


@app.get("/", response_class=HTMLResponse)
def serve_app():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def serve_admin():
    html_path = Path(__file__).parent / "static" / "admin.html"
    return html_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
