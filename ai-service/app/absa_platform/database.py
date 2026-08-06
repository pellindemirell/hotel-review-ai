"""
HCOS ABSA Review Platform v2 — PostgreSQL Database Layer

Dual database conceptualization mapped to PostgreSQL tables:
  1. source — Ham yorumlar, kullanici atamalari, auto-ABSA, duzeltmeler
  2. gold — Insan onayindan gecmis, egitimde kullanilacak temiz veri
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent

PG_CONN_URL = os.getenv(
    "POSTGRES_DB_URL",
    os.getenv("DATABASE_URL", "postgresql://stajor1:stajor1*-@192.168.40.140:5432/stajor")
)
# Convert asyncpg/sqlalchemy URL to standard psycopg2 URL
if PG_CONN_URL.startswith("postgresql+asyncpg://"):
    PG_CONN_URL = PG_CONN_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


# ── PostgreSQL Compatibility Wrapper ─────────────────────────────────

class PostgresCompatRow(dict):
    def __init__(self, dict_row):
        super().__init__(dict_row)
        self._values = list(dict_row.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class PostgresCompatCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        if not self.cursor:
            return None
        row = self.cursor.fetchone()
        return PostgresCompatRow(row) if row is not None else None

    def fetchall(self):
        if not self.cursor:
            return []
        rows = self.cursor.fetchall()
        return [PostgresCompatRow(r) for r in rows]

    def __iter__(self):
        if not self.cursor:
            return
        for row in self.cursor:
            yield PostgresCompatRow(row)

    def close(self):
        if self.cursor:
            self.cursor.close()

    @property
    def rowcount(self):
        return self.cursor.rowcount if self.cursor else 0


class PostgresCompatConnection:
    def __init__(self, conn):
        self.conn = conn

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, val):
        pass

    def execute(self, query, params=None):
        # Skip SQLite specific PRAGMAs
        if query.strip().upper().startswith("PRAGMA"):
            return PostgresCompatCursor(None)

        # 1. Convert SQLite ? to PostgreSQL %s
        query = query.replace("?", "%s")
        
        # 2. Convert SQLite specific SQL commands
        if "INSERT OR IGNORE INTO users" in query:
            query = query.replace("INSERT OR IGNORE INTO users", "INSERT INTO users") + " ON CONFLICT (username) DO NOTHING"
        elif "INSERT OR IGNORE INTO reviews" in query:
            query = query.replace("INSERT OR IGNORE INTO reviews", "INSERT INTO reviews") + " ON CONFLICT (id) DO NOTHING"
        elif "INSERT OR REPLACE INTO gold_reviews" in query:
            query = query.replace("INSERT OR REPLACE INTO gold_reviews", "INSERT INTO gold_reviews") + \
                    " ON CONFLICT (review_id) DO UPDATE SET " \
                    "review_text = EXCLUDED.review_text, " \
                    "review_text_translated = EXCLUDED.review_text_translated, " \
                    "language = EXCLUDED.language, " \
                    "rating = EXCLUDED.rating, " \
                    "hotel_name = EXCLUDED.hotel_name, " \
                    "source = EXCLUDED.source, " \
                    "aspects_json = EXCLUDED.aspects_json, " \
                    "departments_json = EXCLUDED.departments_json, " \
                    "clauses_json = EXCLUDED.clauses_json, " \
                    "failures_json = EXCLUDED.failures_json, " \
                    "corrected_by = EXCLUDED.corrected_by, " \
                    "corrected_at = EXCLUDED.corrected_at, " \
                    "reviewer_username = EXCLUDED.reviewer_username, " \
                    "quality_score = EXCLUDED.quality_score"

        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(query, params)
        return PostgresCompatCursor(cur)

    def executescript(self, script):
        # Execute script directly on the database
        script = script.replace("?", "%s")
        cur = self.conn.cursor()
        cur.execute(script)
        cur.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


# ── Kaynak DB (source) Schema ───────────────────────────────────────

SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'reviewer',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    review_text TEXT NOT NULL,
    review_text_translated TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    rating INTEGER,
    hotel_name TEXT DEFAULT '',
    source TEXT DEFAULT 'google_maps',
    raw_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS absa_auto (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id),
    aspects_json TEXT NOT NULL DEFAULT '[]',
    departments_json TEXT NOT NULL DEFAULT '[]',
    clauses_json TEXT NOT NULL DEFAULT '[]',
    failures_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_assignments (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS absa_corrections (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    field_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assignments_user ON review_assignments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_assignments_review ON review_assignments(review_id);
CREATE INDEX IF NOT EXISTS idx_corrections_review ON absa_corrections(review_id);
CREATE INDEX IF NOT EXISTS idx_corrections_user ON absa_corrections(user_id);
"""

# ── Gold DB (egitim verisi) Schema ──────────────────────────────────

GOLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS gold_reviews (
    id TEXT PRIMARY KEY,
    review_id TEXT UNIQUE NOT NULL,
    review_text TEXT NOT NULL,
    review_text_translated TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    rating INTEGER,
    hotel_name TEXT DEFAULT '',
    source TEXT DEFAULT '',
    aspects_json TEXT NOT NULL DEFAULT '[]',
    departments_json TEXT NOT NULL DEFAULT '[]',
    clauses_json TEXT NOT NULL DEFAULT '[]',
    failures_json TEXT NOT NULL DEFAULT '[]',
    corrected_by TEXT NOT NULL,
    corrected_at TEXT NOT NULL,
    reviewer_username TEXT NOT NULL,
    quality_score REAL DEFAULT 100.0
);

CREATE INDEX IF NOT EXISTS idx_gold_language ON gold_reviews(language);
"""


# ── Baglanti yardimcilari ────────────────────────────────────────────

@contextmanager
def get_source_db():
    raw_conn = psycopg2.connect(PG_CONN_URL)
    conn = PostgresCompatConnection(raw_conn)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_gold_db():
    raw_conn = psycopg2.connect(PG_CONN_URL)
    conn = PostgresCompatConnection(raw_conn)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_dbs():
    with get_source_db() as db:
        db.executescript(SOURCE_SCHEMA)
    with get_gold_db() as db:
        db.executescript(GOLD_SCHEMA)
    print(f"Connected to PostgreSQL: {PG_CONN_URL}")


# ── Veri aktarim: kaynak → gold ─────────────────────────────────────

def push_to_gold(
    review_id: str,
    aspects: list[dict],
    departments: list[dict],
    reviewer_username: str,
    quality_score: float = 100.0,
) -> bool:
    """Onaylanan/duzeltilen yorumu gold DB'ye ekler."""
    with get_source_db() as sdb:
        review = sdb.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        absa = sdb.execute(
            "SELECT clauses_json, failures_json FROM absa_auto WHERE review_id=?",
            (review_id,),
        ).fetchone()

    if not review:
        return False

    with get_gold_db() as gdb:
        gdb.execute(
            """INSERT OR REPLACE INTO gold_reviews
               (id, review_id, review_text, review_text_translated, language, rating,
                hotel_name, source, aspects_json, departments_json, clauses_json,
                failures_json, corrected_by, corrected_at, reviewer_username, quality_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                review_id,
                review["review_text"],
                review["review_text_translated"] or "",
                review["language"],
                review["rating"],
                review["hotel_name"] or "",
                review["source"] or "",
                json.dumps(aspects, ensure_ascii=False),
                json.dumps(departments, ensure_ascii=False),
                absa["clauses_json"] if absa else "[]",
                absa["failures_json"] if absa else "[]",
                reviewer_username,
                datetime.now(timezone.utc).isoformat(),
                reviewer_username,
                quality_score,
            ),
        )
    return True


# ── Kaynak DB islemleri ──────────────────────────────────────────────

def import_reviews_from_json(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with get_source_db() as db:
        existing = set(row["id"] for row in db.execute("SELECT id FROM reviews").fetchall())

        imported = 0
        for ann in data:
            rid = ann.get("review_id", str(uuid.uuid4())[:8])
            if rid in existing:
                continue
            db.execute(
                """INSERT OR IGNORE INTO reviews
                   (id, review_text, review_text_translated, language, rating, hotel_name, source, raw_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid,
                    ann.get("review_text", ""),
                    ann.get("review_text_translated", ""),
                    ann.get("language", "en"),
                    ann.get("rating"),
                    ann.get("hotel_name", "Crystal Waterworld Resort & Spa"),
                    ann.get("source", "google_maps"),
                    json.dumps(ann, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            # Enhanced ABSA engine ile analiz (varsa ceviri kullan)
            from .absa_engine import analyze_batch
            source_text = ann.get("review_text_translated") or ann.get("review_text", "")
            absa_result = analyze_batch(source_text)
            aspects = absa_result.get("clauses", [])
            departments = list(set(a.get("department", "diger") for a in aspects))
            departments_list = [{"department": d} for d in departments]

            db.execute(
                """INSERT INTO absa_auto
                   (id, review_id, aspects_json, departments_json, clauses_json, failures_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    rid,
                    json.dumps(aspects, ensure_ascii=False),
                    json.dumps(departments_list, ensure_ascii=False),
                    json.dumps([c["text"] for c in aspects], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            imported += 1

    print(f"Imported {imported} reviews into source DB")


def seed_users():
    users = [
        ("admin", "Admin", "admin"),
        ("arda1", "Arda Tasci", "reviewer"),
        ("arda2", "Arda Yilmaz", "reviewer"),
        ("pelin", "Pelin", "reviewer"),
        ("bahriye", "Bahriye", "reviewer"),
        ("huseyin", "Huseyin", "reviewer"),
        ("ozgur", "Ozgur", "reviewer"),
    ]
    with get_source_db() as db:
        for username, display_name, role in users:
            db.execute(
                """INSERT OR IGNORE INTO users (id, username, display_name, role, is_active, created_at)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (
                    str(uuid.uuid4()),
                    username,
                    display_name,
                    role,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    print(f"Seeded {len(users)} users")


def assign_reviews_batch(limit: int = 500):
    with get_source_db() as db:
        reviewers = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM users WHERE role='reviewer' AND is_active=1"
            ).fetchall()
        ]
        if not reviewers:
            print("No reviewers found!")
            return

        unassigned = db.execute(
            """SELECT r.id FROM reviews r
               LEFT JOIN review_assignments ra ON r.id = ra.review_id
               WHERE ra.id IS NULL
               LIMIT ?""",
            (limit,),
        ).fetchall()

        for i, row in enumerate(unassigned):
            reviewer_id = reviewers[i % len(reviewers)]
            db.execute(
                """INSERT INTO review_assignments (id, review_id, user_id, status, assigned_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (
                    str(uuid.uuid4()),
                    row["id"],
                    reviewer_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        print(f"Assigned {len(unassigned)} reviews to {len(reviewers)} reviewers")


# ── Gold DB sorgulari ────────────────────────────────────────────────

def get_gold_stats() -> dict:
    with get_gold_db() as db:
        total = db.execute("SELECT COUNT(*) FROM gold_reviews").fetchone()[0]
        langs = db.execute(
            "SELECT language, COUNT(*) as cnt FROM gold_reviews GROUP BY language"
        ).fetchall()
        return {"total": total, "languages": {r["language"]: r["cnt"] for r in langs}}


def export_gold_for_training(limit: int = 0) -> list[dict]:
    with get_gold_db() as db:
        query = "SELECT * FROM gold_reviews ORDER BY corrected_at DESC"
        if limit:
            query += f" LIMIT {limit}"
        rows = db.execute(query).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_dbs()
    seed_users()
    json_path = r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002_translated.json"
    if Path(json_path).exists():
        import_reviews_from_json(json_path)
    else:
        import_reviews_from_json(
            r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
        )
    assign_reviews_batch(5000)
    print("DB setup complete!")
