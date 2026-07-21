"""
Sürekli öğrenme (continuous / reinforcement learning) servisi.

Her analiz edilen yorum learning_buffer'a yazılır; eşik aşıldığında veya
manuel tetiklemede kategori modeli (SGD partial_fit) ve RAG indeksi güncellenir.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.turkish_nlp_utils import ALL_CATEGORIES

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
BUFFER_DIR = os.path.join(_PROJECT_ROOT, "simulation", "learning_buffer")
REVIEWS_FILE = os.path.join(BUFFER_DIR, "reviews_labeled.jsonl")
ASPECTS_FILE = os.path.join(BUFFER_DIR, "aspects_labeled.jsonl")
CORRECTIONS_FILE = os.path.join(BUFFER_DIR, "corrections.jsonl")
META_FILE = os.path.join(BUFFER_DIR, "meta.json")

RETRAIN_THRESHOLD = int(os.getenv("LEARNING_RETRAIN_THRESHOLD", "50"))
CORRECTION_WEIGHT = 3

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_buffer_dir() -> None:
    os.makedirs(BUFFER_DIR, exist_ok=True)


def _load_meta() -> dict[str, Any]:
    _ensure_buffer_dir()
    if not os.path.isfile(META_FILE):
        return {
            "bootstrap_done": False,
            "last_retrain": None,
            "accuracy_before": None,
            "accuracy_after": None,
            "total_retrains": 0,
            "samples_trained_last": 0,
        }
    try:
        with open(META_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"bootstrap_done": False, "last_retrain": None}


def _save_meta(meta: dict[str, Any]) -> None:
    _ensure_buffer_dir()
    with open(META_FILE, encoding="utf-8", mode="w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _append_jsonl(path: str, record: dict[str, Any]) -> None:
    _ensure_buffer_dir()
    with open(path, encoding="utf-8", mode="a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _count_jsonl(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _read_jsonl(path: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(rows) >= limit:
                break
    return rows


class LearningService:
    """Yorum analizi sonrası otomatik öğrenme + incremental retrain."""

    def __init__(self) -> None:
        _ensure_buffer_dir()
        self._maybe_bootstrap()

    def _maybe_bootstrap(self) -> None:
        meta = _load_meta()
        if meta.get("bootstrap_done"):
            return
        with _lock:
            meta = _load_meta()
            if meta.get("bootstrap_done"):
                return
            imported = self._bootstrap_existing_data()
            meta["bootstrap_done"] = True
            meta["bootstrap_imported"] = imported
            meta["bootstrap_at"] = _utc_now()
            _save_meta(meta)

    def _bootstrap_existing_data(self) -> int:
        """Demo yorumlar + CSV analiz verilerini learning buffer'a aktar."""
        count = 0
        try:
            from app.services.review_store import DEMO_REVIEWS
            from app.services.category_service import CategoryService

            cs = CategoryService()
            for comment, rating in DEMO_REVIEWS[:30]:
                cat, conf, method, _, _ = cs.classify_category(comment, use_gemini=False)
                from app.services.sentiment_service import SentimentService
                sentiment, score = SentimentService.analyze_sentiment(comment, rating)
                rid = f"demo-{hash(comment) & 0xFFFFFF:06x}"
                self._store_review_record(
                    review_id=rid,
                    comment=comment,
                    rating=rating,
                    category=cat,
                    sentiment=sentiment,
                    sentiment_score=score,
                    confidence=conf,
                    source="bootstrap_demo",
                    classification_method=method,
                )
                count += 1
        except Exception:
            pass

        sim_dir = os.path.join(_PROJECT_ROOT, "simulation")
        csv_sources = [
            ("scraped_analyzed_reviews.csv", "scraped"),
            ("crystal_waterworld_analyzed_reviews.csv", "crystal"),
            ("processed_reviews_25k.csv", "25k"),
        ]
        text_cols = ("translated_comment", "original_comment", "comment", "text")
        for filename, tag in csv_sources:
            path = os.path.join(sim_dir, filename)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        if i >= 100:
                            break
                        text_col = next((c for c in text_cols if c in row and row.get(c)), None)
                        if not text_col:
                            continue
                        comment = (row.get(text_col) or "").strip()
                        if len(comment) < 5:
                            continue
                        rating_raw = row.get("rating")
                        try:
                            rating = int(float(rating_raw)) if rating_raw else None
                        except (TypeError, ValueError):
                            rating = None
                        self._store_review_record(
                            review_id=f"csv-{tag}-{i}",
                            comment=comment,
                            rating=rating,
                            category=row.get("category", "Diğer"),
                            sentiment=row.get("sentiment", "Neutral"),
                            sentiment_score=float(row.get("sentiment_score", 0) or 0),
                            confidence=float(row.get("confidence", 0.7) or 0.7),
                            source=f"bootstrap_{tag}",
                        )
                        count += 1
            except OSError:
                continue
        return count

    def _store_review_record(
        self,
        review_id: str,
        comment: str,
        rating: Optional[int],
        category: str,
        sentiment: str,
        sentiment_score: float,
        confidence: float,
        source: str,
        classification_method: str = "",
        keywords: Optional[list] = None,
        absa_aspects: Optional[list] = None,
        weight: int = 1,
    ) -> dict[str, Any]:
        record = {
            "id": review_id or str(uuid.uuid4())[:8],
            "comment": comment,
            "rating": rating,
            "category": category,
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "confidence": confidence,
            "classification_method": classification_method,
            "keywords": keywords or [],
            "source": source,
            "weight": weight,
            "stored_at": _utc_now(),
        }
        _append_jsonl(REVIEWS_FILE, record)
        if absa_aspects:
            for asp in absa_aspects:
                _append_jsonl(
                    ASPECTS_FILE,
                    {
                        "review_id": record["id"],
                        "comment": comment,
                        "aspect": asp.get("aspect", ""),
                        "department": asp.get("department", asp.get("departmentLabel", "")),
                        "sentiment": asp.get("sentiment", ""),
                        "sentiment_score": asp.get("sentimentScore", asp.get("sentiment_score", 0)),
                        "confidence": asp.get("confidence", 0.5),
                        "domain": asp.get("domain", "hotel"),
                        "stored_at": _utc_now(),
                    },
                )
        return record

    def evaluate_prediction(
        self,
        predicted_category: str,
        predicted_sentiment: str,
        confidence: float,
        correct_category: Optional[str] = None,
        correct_sentiment: Optional[str] = None,
    ) -> dict[str, Any]:
        """Tahmin kalitesini değerlendir."""
        quality = "high" if confidence >= 0.85 else "medium" if confidence >= 0.65 else "low"
        result: dict[str, Any] = {
            "confidence": confidence,
            "quality": quality,
            "category_match": None,
            "sentiment_match": None,
        }
        if correct_category:
            result["category_match"] = predicted_category == correct_category
            result["quality"] = "corrected" if not result["category_match"] else "confirmed"
        if correct_sentiment:
            result["sentiment_match"] = (
                predicted_sentiment.lower() == correct_sentiment.lower()
            )
        return result

    def record_from_analysis(
        self,
        review_id: str,
        comment: str,
        rating: Optional[int],
        analysis: dict[str, Any],
        absa_aspects: Optional[list] = None,
        source: str = "live",
    ) -> dict[str, Any]:
        """analyze-review sonrası otomatik öğrenme kaydı."""
        with _lock:
            record = self._store_review_record(
                review_id=review_id,
                comment=comment,
                rating=rating,
                category=analysis.get("category", "Diğer"),
                sentiment=analysis.get("sentiment", "Neutral"),
                sentiment_score=float(analysis.get("sentimentScore", 0)),
                confidence=float(analysis.get("confidence", 0.5)),
                classification_method=analysis.get("classificationMethod", ""),
                keywords=analysis.get("keywords"),
                absa_aspects=absa_aspects,
                source=source,
            )
            self._update_department_absa(absa_aspects)
        try:
            from app.services.learning_store import get_learning_store
            from app.services.incremental_trainer import get_incremental_trainer
            get_learning_store().save_prediction(
                review_id=review_id,
                comment=comment,
                rating=rating,
                ai_prediction=analysis,
                source=source,
                keywords=analysis.get("keywords"),
                aspects=absa_aspects,
            )
            get_incremental_trainer().add_training_sample(
                review=comment,
                labels={
                    "category": analysis.get("category", "Diğer"),
                    "sentiment": analysis.get("sentiment", "Neutral"),
                    "keywords": analysis.get("keywords") or [],
                    "aspects": absa_aspects or [],
                },
                ai_prediction=analysis,
                rating=rating,
                source=source,
                weight=1,
                review_id=review_id,
            )
        except Exception:
            pass
        should = self.should_retrain()
        return {
            "stored": True,
            "review_id": record["id"],
            "buffer_size": self.get_buffer_size(),
            "should_retrain": should,
        }

    def _update_department_absa(self, aspects: Optional[list]) -> None:
        if not aspects:
            return
        try:
            from app.services.review_store import get_review_store
            get_review_store().add_absa_aspects("learning", aspects)
        except Exception:
            pass

    def record_correction(
        self,
        review_id: str,
        correct_category: str,
        correct_sentiment: str,
        notes: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Kullanıcı düzeltmesi — 3x ağırlıkla buffer'a eklenir."""
        correction = {
            "id": str(uuid.uuid4())[:8],
            "review_id": review_id,
            "correct_category": correct_category,
            "correct_sentiment": correct_sentiment,
            "notes": notes,
            "comment": comment,
            "weight": CORRECTION_WEIGHT,
            "stored_at": _utc_now(),
        }
        with _lock:
            _append_jsonl(CORRECTIONS_FILE, correction)
            if comment:
                self._store_review_record(
                    review_id=review_id or correction["id"],
                    comment=comment,
                    rating=None,
                    category=correct_category,
                    sentiment=correct_sentiment,
                    sentiment_score=0.0,
                    confidence=1.0,
                    source="user_correction",
                    weight=CORRECTION_WEIGHT,
                )
        return {
            "stored": True,
            "correction_id": correction["id"],
            "weight": CORRECTION_WEIGHT,
            "buffer_size": self.get_buffer_size(),
        }

    def get_buffer_size(self) -> int:
        return _count_jsonl(REVIEWS_FILE)

    def should_retrain(self) -> bool:
        return self.get_buffer_size() >= RETRAIN_THRESHOLD

    def get_stats(self) -> dict[str, Any]:
        meta = _load_meta()
        reviews_count = _count_jsonl(REVIEWS_FILE)
        aspects_count = _count_jsonl(ASPECTS_FILE)
        corrections_count = _count_jsonl(CORRECTIONS_FILE)
        pending = max(0, RETRAIN_THRESHOLD - (reviews_count % RETRAIN_THRESHOLD))
        if reviews_count == 0:
            pending = RETRAIN_THRESHOLD
        stats = {
            "buffer": {
                "reviews": reviews_count,
                "aspects": aspects_count,
                "corrections": corrections_count,
                "total": reviews_count,
            },
            "retrain_threshold": RETRAIN_THRESHOLD,
            "pending_until_retrain": pending if reviews_count > 0 else RETRAIN_THRESHOLD,
            "should_retrain": self.should_retrain(),
            "correction_weight": CORRECTION_WEIGHT,
            "last_retrain": meta.get("last_retrain"),
            "accuracy_before": meta.get("accuracy_before"),
            "accuracy_after": meta.get("accuracy_after"),
            "total_retrains": meta.get("total_retrains", 0),
            "samples_trained_last": meta.get("samples_trained_last", 0),
            "bootstrap_done": meta.get("bootstrap_done", False),
            "bootstrap_imported": meta.get("bootstrap_imported", 0),
        }
        try:
            from app.services.incremental_trainer import get_incremental_trainer
            from app.services.learning_store import get_learning_store
            trainer_stats = get_incremental_trainer().get_training_stats()
            store_stats = get_learning_store().get_stats()
            stats["training_data"] = trainer_stats
            stats["feedback_store"] = store_stats
            stats["category_distribution"] = trainer_stats.get("category_distribution") or store_stats.get("category_distribution", [])
        except Exception:
            pass
        return stats

    def get_recent_buffer(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = _read_jsonl(REVIEWS_FILE)
        return list(reversed(rows[-limit:]))

    def run_retrain(self, category_service=None, force: bool = False) -> dict[str, Any]:
        """Incremental retrain — simulation/incremental_train modülünü çağırır."""
        if not force and not self.should_retrain() and self.get_buffer_size() < 5:
            return {
                "status": "skipped",
                "message": f"Buffer yetersiz (min 5, eşik {RETRAIN_THRESHOLD})",
                "buffer_size": self.get_buffer_size(),
            }
        meta = _load_meta()
        meta["accuracy_before"] = meta.get("accuracy_after")

        try:
            from app.services.incremental_trainer import get_incremental_trainer
            trainer = get_incremental_trainer()
            result = trainer.retrain_category_model(
                min_samples=5 if force else 10,
                reload_category_service=category_service,
            )
            if result.get("status") == "skipped":
                import sys
                sim_dir = os.path.join(_PROJECT_ROOT, "simulation")
                if sim_dir not in sys.path:
                    sys.path.insert(0, sim_dir)
                from incremental_train import run_incremental_training
                result = run_incremental_training(
                    buffer_dir=BUFFER_DIR,
                    reload_category_service=category_service,
                )
            else:
                rag_result = trainer.update_rag_index()
                result["rag_appended"] = rag_result.get("appended", 0)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        meta["last_retrain"] = _utc_now()
        meta["accuracy_after"] = result.get("accuracy")
        meta["total_retrains"] = meta.get("total_retrains", 0) + 1
        meta["samples_trained_last"] = result.get("samples_trained", 0)
        meta["rag_appended"] = result.get("rag_appended", 0)
        _save_meta(meta)

        return {
            "status": "success",
            "message": "Incremental retrain tamamlandı",
            "accuracy_before": meta.get("accuracy_before"),
            "accuracy_after": result.get("accuracy"),
            "samples_trained": result.get("samples_trained", result.get("samples", 0)),
            "rag_appended": result.get("rag_appended", 0),
            "buffer_size": self.get_buffer_size(),
        }


_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _service
    if _service is None:
        _service = LearningService()
    return _service
