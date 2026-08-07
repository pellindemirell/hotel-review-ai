"""
Toplu (bulk) öğrenme — tüm etiketli/analiz edilmiş yorumlardan cümlecik bazlı eğitim.

Crystal CSV'leri, batch analiz JSON, learning buffer ve isteğe bağlı mega_reviews
kaynaklarından aspect-departman-duygu örnekleri üretir; learning_store + incremental_trainer'a yazar.
"""

from __future__ import annotations

import logging

import csv
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SIM_DIR = os.path.join(_PROJECT_ROOT, "simulation")
DATA_DIR = os.path.join(SIM_DIR, "data")
TRAINING_DIR = os.path.join(SIM_DIR, "training_data")
BULK_META_PATH = os.path.join(TRAINING_DIR, "bulk_train_meta.json")

DEFAULT_CSV_GLOBS = [
    "crystal_merged_reviews.csv",
    "crystal_google_reviews.csv",
    "crystal_playwright_reviews.csv",
    "crystal_combined_final.csv",
    "crystal_chrome_cdp_reviews.csv",
    "crystal_playwright_live_merged.csv",
    "playwright_collected_reviews.csv",
    "collected_reviews.csv",
]

TEXT_COLUMNS = (
    "review_text", "translated_comment", "original_comment", "comment", "text", "review",
)
RATING_COLUMNS = ("rating", "stars", "score")
CATEGORY_COLUMNS = ("category", "department", "department_label", "departmentLabel")
SENTIMENT_COLUMNS = ("sentiment", "overall_sentiment", "overallSentiment")

# ABSA departman → kategori modeli etiketi
DEPT_TO_CATEGORY: dict[str, str] = {
    "Housekeeping": "Kat Hizmetleri & Temizlik",
    "Kat Hizmetleri & Temizlik": "Kat Hizmetleri & Temizlik",
    "Restaurant": "Yiyecek & İçecek & Yemekler",
    "Bar": "Yiyecek & İçecek & Yemekler",
    "Yiyecek & İçecek & Yemekler": "Yiyecek & İçecek & Yemekler",
    "Front Office": "Resepsiyon & Ön Büro",
    "Resepsiyon & Ön Büro": "Resepsiyon & Ön Büro",
    "Teknik": "Teknik Servis (Maintenance)",
    "Teknik Servis (Maintenance)": "Teknik Servis (Maintenance)",
    "Spa": "Spa & Wellness / Aktivite",
    "Animasyon & Etkinlik": "Spa & Wellness / Aktivite",
    "Havuz": "Spa & Wellness / Aktivite",
    "Personel": "Personel Davranışı & İletişim",
    "Personel Davranışı & İletişim": "Personel Davranışı & İletişim",
    "Muhasebe & Finans": "Muhasebe & Finans",
    "Genel": "Diğer",
    "Diğer": "Diğer",
    "Dijital": "Diğer",
    "Takip": "Resepsiyon & Ön Büro",
    "Çağrı Merkezi": "Diğer",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dept_to_category(dept: str) -> str:
    d = (dept or "").strip()
    if not d:
        return "Diğer"
    return DEPT_TO_CATEGORY.get(d, DEPT_TO_CATEGORY.get(d.title(), "Diğer"))


def _pick_col(row: dict[str, Any], candidates: tuple[str, ...]) -> Optional[str]:
    for c in candidates:
        if c in row and row.get(c):
            return c
    lower_map = {k.lower(): k for k in row}
    for c in candidates:
        if c.lower() in lower_map and row.get(lower_map[c.lower()]):
            return lower_map[c.lower()]
    return None


def _parse_rating(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        v = int(float(str(raw).replace(",", ".")))
        return v if 1 <= v <= 5 else None
    except (TypeError, ValueError):
        return None


def _normalize_sentiment(s: str) -> str:
    s = (s or "Neutral").strip()
    low = s.lower()
    if low in ("positive", "olumlu", "pos"):
        return "Positive"
    if low in ("negative", "olumsuz", "neg"):
        return "Negative"
    return "Neutral"


class BulkTrainer:
    """Tüm kaynaklardan toplu eğitim verisi üretir ve modelleri günceller."""

    def __init__(self, reviews_dir: Optional[str] = None) -> None:
        self.reviews_dir = reviews_dir or DATA_DIR
        os.makedirs(TRAINING_DIR, exist_ok=True)

    def discover_csv_files(self, extra_dir: Optional[str] = None) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for base in filter(None, [self.reviews_dir, extra_dir]):
            if not base or not os.path.isdir(base):
                continue
            for name in DEFAULT_CSV_GLOBS:
                p = os.path.join(base, name)
                if os.path.isfile(p) and p not in seen:
                    seen.add(p)
                    paths.append(p)
        return sorted(paths)

    @staticmethod
    def dedupe_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for r in reviews:
            key = (r.get("comment") or "")[:300].lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def load_reviews_from_jsonl(
        self,
        path: str,
        max_rows: Optional[int] = None,
        text_field: str = "review",
    ) -> list[dict[str, Any]]:
        """JSONL kaynaklarından yorum yükle (normalized/labeled)."""
        rows: list[dict[str, Any]] = []
        if not os.path.isfile(path):
            return rows
        try:
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if max_rows and i >= max_rows:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    comment = (row.get(text_field) or row.get("comment") or row.get("text") or "").strip()
                    if len(comment) < 8:
                        continue
                    rating = _parse_rating(row.get("rating"))
                    sentiment_obj = row.get("sentiment")
                    sentiment = ""
                    if isinstance(sentiment_obj, dict):
                        overall = sentiment_obj.get("overall", "")
                        sentiment = overall.capitalize() if overall else ""
                    elif isinstance(sentiment_obj, str):
                        sentiment = sentiment_obj
                    dept = ""
                    if row.get("departments"):
                        dept = row["departments"][0] if isinstance(row["departments"], list) else str(row["departments"])
                    rows.append({
                        "review_id": row.get("review_id", f"jsonl-{os.path.basename(path)}-{i}"),
                        "comment": comment,
                        "rating": rating,
                        "category": dept,
                        "sentiment": sentiment,
                        "source": f"jsonl:{os.path.basename(path)}",
                        "aspects": row.get("aspects") or [],
                    })
        except OSError:
            logging.getLogger(__name__).debug("load_reviews_from_jsonl: hata yutuldu", exc_info=True)
        return rows

    def load_marrakesh_labeled_samples(self, path: str, max_rows: int = 5000) -> list[dict[str, Any]]:
        """Marrakesh labeled JSONL — aspect etiketleri varsa doğrudan kullan."""
        samples: list[dict[str, Any]] = []
        if not os.path.isfile(path):
            return samples
        try:
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= max_rows:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    comment = (row.get("review") or row.get("comment") or "").strip()
                    if len(comment) < 10:
                        continue
                    rating = _parse_rating(row.get("rating"))
                    aspects = row.get("aspects") or []
                    if aspects:
                        for j, asp in enumerate(aspects):
                            clause = (asp.get("clause") or asp.get("text") or comment[:200]).strip()
                            dept = asp.get("departmentLabel") or asp.get("department") or "Genel"
                            sent = _normalize_sentiment(asp.get("sentiment", row.get("sentiment", {}).get("overall", "Neutral") if isinstance(row.get("sentiment"), dict) else "Neutral"))
                            samples.append({
                                "review_id": f"marr-{i}-{j}",
                                "comment": clause,
                                "full_review": comment,
                                "rating": rating,
                                "category": _dept_to_category(dept),
                                "department": dept,
                                "sentiment": sent,
                                "source": "marrakesh_labeled",
                                "weight": 3,
                            })
                    else:
                        samples.append({
                            "review_id": f"marr-{i}",
                            "comment": comment[:300],
                            "full_review": comment,
                            "rating": rating,
                            "category": "Diğer",
                            "department": "Genel",
                            "sentiment": _normalize_sentiment(
                                row.get("sentiment", {}).get("overall", "Neutral") if isinstance(row.get("sentiment"), dict) else "Neutral"
                            ),
                            "source": "marrakesh_labeled",
                            "weight": 1,
                        })
        except OSError:
            logging.getLogger(__name__).debug("load_marrakesh_labeled_samples: hata yutuldu", exc_info=True)
        return samples

    def discover_data_sources(self, data_dir: str, max_rows: Optional[int] = None) -> tuple[list[str], list[str]]:
        """combined dizininden CSV + JSONL keşfi."""
        csv_paths = self.discover_csv_files(extra_dir=data_dir)
        jsonl_paths: list[str] = []
        for name in (
            "combined/normalized_all.jsonl",
            "combined/labeled_all.jsonl",
            "combined/labeled/marrakesh_labeled.jsonl",
            "combined/normalized/european.jsonl",
            "combined/marrakesh_train.csv",
        ):
            p = os.path.join(data_dir, name) if not os.path.isabs(name) else name
            if os.path.isfile(p):
                jsonl_paths.append(p)
        return csv_paths, jsonl_paths

    def load_reviews_from_csv(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not os.path.isfile(path):
            return rows
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    text_col = _pick_col(row, TEXT_COLUMNS)
                    if not text_col:
                        continue
                    comment = (row.get(text_col) or "").strip()
                    if len(comment) < 8:
                        continue
                    rating_col = _pick_col(row, RATING_COLUMNS)
                    rating = _parse_rating(row.get(rating_col)) if rating_col else None
                    cat_col = _pick_col(row, CATEGORY_COLUMNS)
                    category = row.get(cat_col, "") if cat_col else ""
                    sent_col = _pick_col(row, SENTIMENT_COLUMNS)
                    sentiment = row.get(sent_col, "") if sent_col else ""
                    rid = f"bulk-{os.path.basename(path)}-{i}"
                    rows.append({
                        "review_id": rid,
                        "comment": comment,
                        "rating": rating,
                        "category": category,
                        "sentiment": sentiment,
                        "source": f"csv:{os.path.basename(path)}",
                    })
        except OSError:
            logging.getLogger(__name__).debug("load_reviews_from_csv: hata yutuldu", exc_info=True)
        return rows

    def load_batch_analysis_json(self, path: Optional[str] = None) -> list[dict[str, Any]]:
        """crystal_batch_analysis.json — önceden analiz edilmiş aspect etiketleri."""
        path = path or os.path.join(self.reviews_dir, "crystal_batch_analysis.json")
        if not os.path.isfile(path):
            alt = os.path.join(SIM_DIR, "data", "crystal_batch_analysis.json")
            path = alt if os.path.isfile(alt) else path
        if not os.path.isfile(path):
            return []

        samples: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return samples

        reviews = data.get("reviews") or data.get("items") or []
        if isinstance(reviews, dict):
            reviews = list(reviews.values())

        for i, rev in enumerate(reviews):
            if not isinstance(rev, dict):
                continue
            comment = (rev.get("review_text") or rev.get("comment") or rev.get("text") or "").strip()
            rating = _parse_rating(rev.get("rating"))
            absa = (rev.get("absa") or {}).get("aspects") or rev.get("aspects") or []
            for j, asp in enumerate(absa):
                clause = (asp.get("clause") or "").strip()
                if len(clause) < 5:
                    continue
                dept = asp.get("departmentLabel") or asp.get("department") or "Genel"
                samples.append({
                    "review_id": f"batch-{i}-{j}",
                    "comment": clause,
                    "full_review": comment,
                    "rating": rating,
                    "category": _dept_to_category(dept),
                    "department": dept,
                    "sentiment": _normalize_sentiment(asp.get("sentiment", "Neutral")),
                    "keywords": asp.get("keywords") or [],
                    "aspect": asp.get("aspectLabel") or asp.get("aspect", ""),
                    "source": "batch_analysis",
                    "weight": 2,
                })
        return samples

    def generate_absa_samples(
        self,
        reviews: list[dict[str, Any]],
        include_long: bool = True,
        min_clause_len: int = 8,
    ) -> list[dict[str, Any]]:
        """Her yorumu cümleciklere ayır; ontology + sentiment ile hızlı etiket üret."""
        from app.services.absa_service import split_clauses_absa
        from app.services.ontology_service import OntologyService, reload_ontology
        from app.services.sentiment_service import SentimentService
        from app.services.turkish_nlp_utils import detect_strong_sentiment

        reload_ontology()
        samples: list[dict[str, Any]] = []
        seen_clauses: set[str] = set()

        for rev in reviews:
            comment = (rev.get("comment") or "").strip()
            if len(comment) < min_clause_len:
                continue
            rating = rev.get("rating")
            rid = rev.get("review_id", f"absa-{hash(comment) & 0xFFFFFF:06x}")

            clauses = split_clauses_absa(comment) if (include_long or len(comment.split()) > 15) else [comment]

            for clause in clauses:
                ck = clause.lower().strip()
                if ck in seen_clauses or len(clause) < min_clause_len:
                    continue
                seen_clauses.add(ck)

                mapping = OntologyService.map_aspect_to_department(comment, clause)
                dept = mapping.get("departmentLabel", "Genel")
                if dept in ("Genel", "Diğer") and rev.get("category"):
                    dept = rev["category"]

                sentiment, _ = SentimentService.analyze_sentiment(clause, rating=None)
                if sentiment == "Neutral":
                    sentiment, _ = detect_strong_sentiment(clause)

                samples.append({
                    "review_id": f"{rid}-{hash(clause) & 0xFFFF:04x}",
                    "comment": clause,
                    "full_review": comment,
                    "rating": rating,
                    "category": _dept_to_category(dept),
                    "department": dept,
                    "sentiment": _normalize_sentiment(sentiment),
                    "keywords": mapping.get("matchedKeywords") or [],
                    "aspect": mapping.get("aspectLabel", ""),
                    "source": rev.get("source", "absa_generated"),
                    "weight": 2 if len(comment.split()) > 20 else 1,
                })

        return samples

    def ingest_samples(
        self,
        samples: list[dict[str, Any]],
        dedupe: bool = True,
        write_buffer: bool = False,
    ) -> dict[str, Any]:
        """Örnekleri incremental_trainer'a yaz; buffer opsiyonel."""
        from app.services.incremental_trainer import get_incremental_trainer

        trainer = get_incremental_trainer()

        existing: set[str] = set()
        if dedupe:
            try:
                export = trainer.export_training_data()
                for row in export.get("reviews", []):
                    c = (row.get("comment") or "")[:200].lower()
                    if c:
                        existing.add(c)
            except Exception:
                logging.getLogger(__name__).debug("ingest_samples: hata yutuldu", exc_info=True)

        added = 0
        skipped = 0
        pos_words: list[str] = []
        neg_words: list[str] = []

        for s in samples:
            comment = (s.get("comment") or "").strip()
            if len(comment) < 5:
                skipped += 1
                continue
            key = comment[:200].lower()
            if dedupe and key in existing:
                skipped += 1
                continue
            existing.add(key)

            labels = {
                "category": s.get("category", "Diğer"),
                "sentiment": s.get("sentiment", "Neutral"),
                "keywords": s.get("keywords") or [],
                "aspects": [{"aspect": s.get("aspect"), "department": s.get("department")}],
            }
            weight = int(s.get("weight", 1))
            trainer.add_training_sample(
                review=comment,
                labels=labels,
                rating=s.get("rating"),
                source=s.get("source", "bulk_train"),
                weight=weight,
                review_id=s.get("review_id"),
            )

            if write_buffer:
                try:
                    from app.services.learning_service import get_learning_service
                    get_learning_service().record_from_analysis(
                        review_id=s.get("review_id", f"bulk-{added}"),
                        comment=comment,
                        rating=s.get("rating"),
                        analysis={
                            "category": labels["category"],
                            "sentiment": labels["sentiment"],
                            "sentimentScore": 0.0,
                            "confidence": 0.85,
                            "keywords": labels["keywords"],
                        },
                        absa_aspects=[{
                            "aspect": s.get("aspect", ""),
                            "department": s.get("department", ""),
                            "departmentLabel": s.get("department", ""),
                            "sentiment": labels["sentiment"],
                        }],
                        source=f"bulk:{s.get('source', 'train')}",
                    )
                except Exception:
                    logging.getLogger(__name__).debug("ingest_samples: hata yutuldu", exc_info=True)

            sent = labels["sentiment"].lower()
            for kw in labels["keywords"]:
                if sent == "positive":
                    pos_words.append(kw)
                elif sent == "negative":
                    neg_words.append(kw)
            added += 1

        lex_result = {"words_added": 0}
        if pos_words or neg_words:
            lex_result = trainer.retrain_sentiment_lexicon({
                "positive_phrases": pos_words[:200],
                "negative_phrases": neg_words[:200],
            })

        return {
            "added": added,
            "skipped": skipped,
            "lexicon": lex_result,
        }

    def run_bulk_train(
        self,
        csv_paths: Optional[list[str]] = None,
        include_long: bool = True,
        retrain_absa: bool = True,
        export_weights: bool = False,
        include_mega: bool = False,
        mega_limit: int = 500,
        force_retrain: bool = True,
        category_service=None,
        data_dir: Optional[str] = None,
        max_rows: Optional[int] = None,
        jsonl_paths: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Tam bulk pipeline: yükle → ABSA etiketle → kaydet → model eğit."""
        from app.services.incremental_trainer import get_incremental_trainer
        from app.services.learning_service import get_learning_service
        from app.services.ontology_service import reload_ontology

        reload_ontology()
        started = _utc_now()
        stats: dict[str, Any] = {
            "started_at": started,
            "sources": {},
            "samples_total": 0,
        }

        all_reviews: list[dict[str, Any]] = []
        if csv_paths is None:
            csv_paths = self.discover_csv_files()

        if data_dir and os.path.isdir(data_dir):
            extra_csv, discovered_jsonl = self.discover_data_sources(data_dir, max_rows=max_rows)
            for p in extra_csv:
                if p not in csv_paths:
                    csv_paths.append(p)
            if jsonl_paths is None:
                jsonl_paths = discovered_jsonl

        for path in csv_paths:
            rows = self.load_reviews_from_csv(path)
            stats["sources"][os.path.basename(path)] = len(rows)
            all_reviews.extend(rows)

        marrakesh_samples: list[dict[str, Any]] = []
        if jsonl_paths:
            for jpath in jsonl_paths:
                if not os.path.isfile(jpath):
                    continue
                if "marrakesh" in jpath.lower() and "labeled" in jpath.lower():
                    marr = self.load_marrakesh_labeled_samples(jpath, max_rows=max_rows or 5000)
                    stats["sources"][os.path.basename(jpath)] = len(marr)
                    marrakesh_samples.extend(marr)
                elif jpath.endswith(".jsonl"):
                    jrows = self.load_reviews_from_jsonl(jpath, max_rows=max_rows)
                    stats["sources"][os.path.basename(jpath)] = len(jrows)
                    all_reviews.extend(jrows)

        all_reviews = self.dedupe_reviews(all_reviews)
        stats["unique_reviews"] = len(all_reviews)

        batch_samples = self.load_batch_analysis_json()
        stats["sources"]["crystal_batch_analysis.json"] = len(batch_samples)

        absa_samples = self.generate_absa_samples(all_reviews, include_long=include_long)
        stats["sources"]["absa_generated"] = len(absa_samples)

        all_samples = batch_samples + absa_samples + marrakesh_samples

        if include_mega:
            mega_samples = self._sample_mega_reviews(limit=mega_limit)
            stats["sources"]["mega_reviews"] = len(mega_samples)
            all_samples.extend(mega_samples)

        ingest = self.ingest_samples(all_samples, dedupe=True, write_buffer=False)
        stats["ingest"] = ingest
        stats["samples_total"] = ingest["added"]

        trainer = get_incremental_trainer()
        learning = get_learning_service()

        retrain_result: dict[str, Any] = {"status": "skipped"}
        if retrain_absa and ingest["added"] > 0:
            retrain_result = trainer.retrain_category_model(
                min_samples=5,
                reload_category_service=category_service,
            )
            if retrain_result.get("status") == "skipped":
                retrain_result = learning.run_retrain(
                    category_service=category_service,
                    force=force_retrain,
                )
            rag_result = trainer.update_rag_index()
            retrain_result["rag_appended"] = rag_result.get("appended", 0)

        stats["retrain"] = retrain_result

        if export_weights:
            stats["export"] = self.export_weights()

        stats["finished_at"] = _utc_now()
        stats["training_stats"] = trainer.get_training_stats()

        meta = {
            "last_bulk_train": stats["finished_at"],
            "samples_added": ingest["added"],
            "sources": stats["sources"],
            "accuracy": retrain_result.get("accuracy"),
        }
        try:
            with open(BULK_META_PATH, encoding="utf-8", mode="w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            logging.getLogger(__name__).debug("run_bulk_train: hata yutuldu", exc_info=True)

        return stats

    def train_from_csv(self, csv_path: str, include_long: bool = True, **kwargs) -> dict[str, Any]:
        """Tek CSV dosyasından bulk eğitim."""
        return self.run_bulk_train(
            csv_paths=[csv_path],
            include_long=include_long,
            **kwargs,
        )

    def _sample_mega_reviews(self, limit: int = 500) -> list[dict[str, Any]]:
        """mega_reviews_8m/1m — category sütunu varsa örnek al."""
        samples: list[dict[str, Any]] = []
        for name in ("mega_reviews_8m.csv", "mega_reviews_1m.csv"):
            path = os.path.join(SIM_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        if i >= limit:
                            break
                        text_col = _pick_col(row, TEXT_COLUMNS)
                        if not text_col:
                            continue
                        comment = (row.get(text_col) or "").strip()
                        if len(comment) < 10:
                            continue
                        cat_col = _pick_col(row, CATEGORY_COLUMNS)
                        if not cat_col or not row.get(cat_col):
                            continue
                        samples.append({
                            "review_id": f"mega-{i}",
                            "comment": comment,
                            "rating": _parse_rating(row.get(_pick_col(row, RATING_COLUMNS) or "")),
                            "category": row.get(cat_col, "Diğer"),
                            "sentiment": _normalize_sentiment(
                                row.get(_pick_col(row, SENTIMENT_COLUMNS) or "", "Neutral")
                            ),
                            "source": f"mega:{name}",
                            "weight": 1,
                        })
            except OSError:
                continue
            if samples:
                break
        return samples

    def export_weights(self) -> dict[str, Any]:
        """Model ağırlıklarını training_data altına kopyala."""
        import shutil
        from app.services.incremental_trainer import MODEL_PATH, VECTORIZER_PATH, META_PATH

        out_dir = os.path.join(TRAINING_DIR, "exported_weights")
        os.makedirs(out_dir, exist_ok=True)
        copied = []
        for src in (MODEL_PATH, VECTORIZER_PATH, META_PATH, BULK_META_PATH):
            if os.path.isfile(src):
                dst = os.path.join(out_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                copied.append(dst)
        return {"status": "success", "files": copied, "dir": out_dir}


_trainer: Optional[BulkTrainer] = None


def get_bulk_trainer(reviews_dir: Optional[str] = None) -> BulkTrainer:
    global _trainer
    if _trainer is None or (reviews_dir and reviews_dir != _trainer.reviews_dir):
        _trainer = BulkTrainer(reviews_dir=reviews_dir)
    return _trainer
