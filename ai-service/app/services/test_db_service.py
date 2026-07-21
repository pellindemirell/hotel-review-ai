import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "simulation")
_DB_PATH = os.path.join(_DB_DIR, "test_reviews.db")


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS test_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment TEXT NOT NULL,
                rating INTEGER,
                language TEXT DEFAULT 'tr',
                analysis_json TEXT,
                overall_sentiment TEXT,
                overall_score REAL,
                primary_category TEXT,
                is_corrected INTEGER DEFAULT 0,
                corrected_department TEXT,
                corrected_sentiment TEXT,
                corrected_notes TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                corrected_at TEXT
            );

            CREATE TABLE IF NOT EXISTS test_aspects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                clause TEXT,
                department TEXT,
                department_label TEXT,
                aspect TEXT,
                aspect_label TEXT,
                sentiment TEXT,
                sentiment_score REAL,
                confidence REAL,
                priority TEXT,
                is_corrected INTEGER DEFAULT 0,
                corrected_department TEXT,
                corrected_sentiment TEXT,
                FOREIGN KEY (review_id) REFERENCES test_reviews(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
        logger.info("Test DB initialized at %s", _DB_PATH)
    finally:
        conn.close()


def add_review(comment: str, rating: Optional[int], language: str, analysis: dict) -> int:
    conn = _get_conn()
    try:
        aspects = analysis.get("absaAspects") or analysis.get("aspects", [])
        overall_sent = analysis.get("sentiment") or analysis.get("overallSentiment", "Neutral")
        overall_score = analysis.get("sentimentScore") or analysis.get("overallScore", 0.0)
        primary_cat = analysis.get("category") or ""
        cur = conn.execute(
            "INSERT INTO test_reviews (comment, rating, language, analysis_json, overall_sentiment, overall_score, primary_category) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (comment, rating, language, json.dumps(analysis, ensure_ascii=False), overall_sent, overall_score, primary_cat),
        )
        review_id = cur.lastrowid
        for a in aspects:
            conn.execute(
                "INSERT INTO test_aspects (review_id, clause, department, department_label, aspect, aspect_label, sentiment, sentiment_score, confidence, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    a.get("clause") or a.get("text", ""),
                    a.get("department", ""),
                    a.get("departmentLabel") or a.get("department_label", ""),
                    a.get("aspect", ""),
                    a.get("aspectLabel") or a.get("aspect_label", ""),
                    a.get("sentiment", ""),
                    a.get("sentimentScore") or a.get("sentiment_score", 0.0),
                    a.get("confidence", 0.0),
                    a.get("priority", ""),
                ),
            )
        conn.commit()
        return review_id
    finally:
        conn.close()


def list_reviews(limit: int = 50, offset: int = 0, only_uncorrected: bool = False):
    conn = _get_conn()
    try:
        where = "WHERE is_corrected = 0" if only_uncorrected else ""
        rows = conn.execute(
            f"SELECT * FROM test_reviews {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM test_reviews" + (" WHERE is_corrected = 0" if only_uncorrected else "")).fetchone()[0]
        return [dict(r) for r in rows], total
    finally:
        conn.close()


def get_review(review_id: int):
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM test_reviews WHERE id = ?", (review_id,)).fetchone()
        if not row:
            return None
        aspects = conn.execute("SELECT * FROM test_aspects WHERE review_id = ?", (review_id,)).fetchall()
        result = dict(row)
        result["aspects"] = [dict(a) for a in aspects]
        return result
    finally:
        conn.close()


def correct_review(review_id: int, correction: dict):
    conn = _get_conn()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE test_reviews SET is_corrected = 1, corrected_department = ?, corrected_sentiment = ?, corrected_notes = ?, corrected_at = ? WHERE id = ?",
            (
                correction.get("corrected_department", ""),
                correction.get("corrected_sentiment", ""),
                correction.get("notes", ""),
                now,
                review_id,
            ),
        )
        for asp in correction.get("corrected_aspects", []):
            conn.execute(
                "UPDATE test_aspects SET is_corrected = 1, corrected_department = ?, corrected_sentiment = ? WHERE id = ?",
                (
                    asp.get("corrected_department", ""),
                    asp.get("corrected_sentiment", ""),
                    asp.get("id"),
                ),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_review(review_id: int):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM test_aspects WHERE review_id = ?", (review_id,))
        conn.execute("DELETE FROM test_reviews WHERE id = ?", (review_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def export_corrected():
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM test_reviews WHERE is_corrected = 1 ORDER BY corrected_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
