"""
Incremental model trainer — reinforcement learning pipeline.

Training outputs:
  simulation/training_data/incremental_reviews.jsonl
  simulation/training_data/corrections.jsonl
  simulation/training_data/chatbot_dialogues.jsonl
"""

from __future__ import annotations

import logging

import json
import os
import string
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import joblib
import numpy as np
from scipy.sparse import vstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, f1_score

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SIM_DIR = os.path.join(_PROJECT_ROOT, "simulation")
TRAINING_DIR = os.path.join(SIM_DIR, "training_data")
REVIEWS_JSONL = os.path.join(TRAINING_DIR, "incremental_reviews.jsonl")
CORRECTIONS_JSONL = os.path.join(TRAINING_DIR, "corrections.jsonl")
CHATBOT_JSONL = os.path.join(TRAINING_DIR, "chatbot_dialogues.jsonl")
MODEL_PATH = os.path.join(SIM_DIR, "category_model.joblib")
VECTORIZER_PATH = os.path.join(SIM_DIR, "vectorizer.joblib")
RAG_INDEX_PATH = os.path.join(SIM_DIR, "rag_index.joblib")
LEARNED_LEXICON_PATH = os.path.join(SIM_DIR, "hotel_phrase_lexicon_learned.json")
META_PATH = os.path.join(TRAINING_DIR, "trainer_meta.json")

CATEGORIES = [
    "Kat Hizmetleri & Temizlik",
    "Yiyecek & İçecek & Yemekler",
    "Resepsiyon & Ön Büro",
    "Teknik Servis (Maintenance)",
    "Spa & Wellness / Aktivite",
    "Muhasebe & Finans",
    "Personel Davranışı & İletişim",
    "Diğer",
]

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    os.makedirs(TRAINING_DIR, exist_ok=True)


def _append_jsonl(path: str, record: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(path, encoding="utf-8", mode="a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: str) -> list[dict[str, Any]]:
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
    return rows


def _count_jsonl(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def clean_text(text: str) -> str:
    text = str(text).lower()
    return text.translate(str.maketrans("", "", string.punctuation))


def _load_meta() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.isfile(META_PATH):
        return {"last_retrain": None, "accuracy_before": None, "accuracy_after": None, "total_retrains": 0}
    try:
        with open(META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"last_retrain": None, "accuracy_before": None, "accuracy_after": None, "total_retrains": 0}


def _save_meta(meta: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(META_PATH, encoding="utf-8", mode="w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


class IncrementalTrainer:
    """Append training samples and run partial_fit / RAG / lexicon updates."""

    def add_training_sample(
        self,
        review: str,
        labels: dict[str, Any],
        ai_prediction: Optional[dict[str, Any]] = None,
        rating: Optional[int] = None,
        source: str = "manual",
        weight: int = 1,
        review_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Append labeled review to incremental_reviews.jsonl."""
        record = {
            "review_id": review_id or f"inc-{hash(review) & 0xFFFFFF:06x}",
            "comment": review,
            "rating": rating,
            "category": labels.get("category", "Diğer"),
            "sentiment": labels.get("sentiment", "Neutral"),
            "keywords": labels.get("keywords") or [],
            "aspects": labels.get("aspects") or [],
            "ai_prediction": ai_prediction or {},
            "source": source,
            "weight": max(1, weight),
            "stored_at": _utc_now(),
        }
        with _lock:
            _append_jsonl(REVIEWS_JSONL, record)
        return record

    def add_correction_sample(
        self,
        review_id: str,
        comment: str,
        correct_category: str,
        correct_sentiment: str,
        keywords: Optional[list] = None,
        notes: str = "",
        weight: int = 3,
    ) -> dict[str, Any]:
        """Append correction to corrections.jsonl and incremental reviews."""
        record = {
            "review_id": review_id,
            "comment": comment,
            "correct_category": correct_category,
            "correct_sentiment": correct_sentiment,
            "keywords": keywords or [],
            "notes": notes,
            "weight": weight,
            "stored_at": _utc_now(),
        }
        with _lock:
            _append_jsonl(CORRECTIONS_JSONL, record)
        self.add_training_sample(
            review=comment,
            labels={
                "category": correct_category,
                "sentiment": correct_sentiment,
                "keywords": keywords or [],
            },
            rating=None,
            source="correction",
            weight=weight,
            review_id=review_id,
        )
        return record

    def add_chat_dialogue(
        self,
        query: str,
        answer: str,
        accepted: bool = True,
        correction: Optional[str] = None,
        intent: str = "",
        mode: str = "chat",
    ) -> dict[str, Any]:
        """Save chat Q&A pair to chatbot_dialogues.jsonl."""
        record = {
            "query": query,
            "answer": answer,
            "accepted": accepted,
            "correction": correction,
            "intent": intent,
            "mode": mode,
            "stored_at": _utc_now(),
        }
        with _lock:
            _append_jsonl(CHATBOT_JSONL, record)
        return record

    def _load_training_samples(self) -> tuple[list[str], list[str], list[int]]:
        texts: list[str] = []
        labels: list[str] = []
        weights: list[int] = []

        for row in _read_jsonl(REVIEWS_JSONL):
            comment = (row.get("comment") or "").strip()
            if len(comment) < 3:
                continue
            cat = row.get("category", "Diğer")
            w = int(row.get("weight", 1))
            texts.append(clean_text(comment))
            labels.append(cat if cat in CATEGORIES else "Diğer")
            weights.append(max(1, w))

        for row in _read_jsonl(CORRECTIONS_JSONL):
            comment = (row.get("comment") or "").strip()
            cat = row.get("correct_category", "Diğer")
            if not comment:
                continue
            w = int(row.get("weight", 3))
            texts.append(clean_text(comment))
            labels.append(cat if cat in CATEGORIES else "Diğer")
            weights.append(max(1, w))

        return texts, labels, weights

    @staticmethod
    def _expand_weighted(texts: list[str], labels: list[str], weights: list[int]):
        xt, yl = [], []
        for t, l, w in zip(texts, labels, weights):
            for _ in range(w):
                xt.append(t)
                yl.append(l)
        return xt, yl

    def retrain_category_model(
        self,
        min_samples: int = 10,
        reload_category_service=None,
    ) -> dict[str, Any]:
        """Incremental SGDClassifier partial_fit using existing vectorizer."""
        texts, labels, weights = self._load_training_samples()
        if len(texts) < min_samples:
            return {
                "status": "skipped",
                "message": f"Yetersiz örnek ({len(texts)}/{min_samples})",
                "samples": len(texts),
            }

        meta = _load_meta()
        meta["accuracy_before"] = meta.get("accuracy_after")

        xt, yl = self._expand_weighted(texts, labels, weights)

        vectorizer = None
        model = None
        if os.path.isfile(VECTORIZER_PATH):
            try:
                vectorizer = joblib.load(VECTORIZER_PATH)
            except Exception:
                vectorizer = None
        if os.path.isfile(MODEL_PATH):
            try:
                model = joblib.load(MODEL_PATH)
            except Exception:
                model = None

        if vectorizer is None:
            vectorizer = TfidfVectorizer(
                max_features=8000,
                ngram_range=(1, 4),
                sublinear_tf=True,
                min_df=1,
                max_df=0.99,
            )
            vectorizer.fit(xt)

        X = vectorizer.transform(xt)
        if model is None or not hasattr(model, "fit"):
            model = SGDClassifier(
                loss="log_loss",
                alpha=0.0001,
                random_state=42,
                max_iter=1000,
            )
        model.fit(X, yl)

        preds = model.predict(X)
        accuracy = float(accuracy_score(yl, preds))
        try:
            f1 = float(f1_score(yl, preds, average="weighted", zero_division=0))
        except Exception:
            f1 = 0.0

        joblib.dump(model, MODEL_PATH)
        joblib.dump(vectorizer, VECTORIZER_PATH)

        if reload_category_service is not None:
            reload_category_service.model = model
            reload_category_service.vectorizer = vectorizer

        meta["last_retrain"] = _utc_now()
        meta["accuracy_after"] = round(accuracy, 4)
        meta["f1_after"] = round(f1, 4)
        meta["total_retrains"] = meta.get("total_retrains", 0) + 1
        meta["samples_trained_last"] = len(texts)
        _save_meta(meta)

        return {
            "status": "success",
            "samples": len(texts),
            "weighted_samples": sum(weights),
            "accuracy": round(accuracy, 4),
            "f1_weighted": round(f1, 4),
            "accuracy_before": meta.get("accuracy_before"),
        }

    def retrain_sentiment_lexicon(self, new_words: dict[str, list[str]]) -> dict[str, Any]:
        """Add confirmed keywords to learned lexicon file."""
        _ensure_dirs()
        learned: dict[str, Any] = {"meta": {"updated_at": _utc_now(), "source": "incremental_trainer"}}
        if os.path.isfile(LEARNED_LEXICON_PATH):
            try:
                with open(LEARNED_LEXICON_PATH, encoding="utf-8") as f:
                    learned = json.load(f)
            except (OSError, json.JSONDecodeError):
                logging.getLogger(__name__).debug("retrain_sentiment_lexicon: hata yutuldu", exc_info=True)

        added = 0
        for key in ("positive_phrases", "negative_phrases"):
            existing = set(learned.get(key, []))
            for word in new_words.get(key, []):
                w = str(word).strip().lower()
                if not w:
                    continue
                try:
                    from app.services.lexicon_loader import _is_valid_learned_phrase
                    if not _is_valid_learned_phrase(w):
                        continue
                except ImportError:
                    if len(w) < 5 and " " not in w:
                        continue
                if w not in existing:
                    existing.add(w)
                    added += 1
            learned[key] = sorted(existing)

        learned.setdefault("meta", {})["updated_at"] = _utc_now()
        learned["meta"]["total_added"] = learned["meta"].get("total_added", 0) + added

        with open(LEARNED_LEXICON_PATH, encoding="utf-8", mode="w") as f:
            json.dump(learned, f, ensure_ascii=False, indent=2)

        try:
            from app.services.lexicon_loader import load_lexicon
            load_lexicon.cache_clear()
        except Exception:
            logging.getLogger(__name__).debug("retrain_sentiment_lexicon: hata yutuldu", exc_info=True)

        return {"status": "success", "words_added": added, "path": LEARNED_LEXICON_PATH}

    def update_rag_index(self, new_reviews: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Append new records to RAG index without full rebuild."""
        if new_reviews is None:
            new_reviews = []
            for row in _read_jsonl(REVIEWS_JSONL):
                comment = (row.get("comment") or "").strip()
                if len(comment) < 3:
                    continue
                new_reviews.append({
                    "_rag_text": comment,
                    "category": row.get("category", "Bilinmiyor"),
                    "rating": row.get("rating") if row.get("rating") is not None else "N/A",
                    "sentiment": row.get("sentiment", ""),
                    "source": f"training:{row.get('source', 'incremental')}",
                    "_origin": "training_data",
                    "department": row.get("category", ""),
                    "stored_at": row.get("stored_at", ""),
                })

        if not new_reviews:
            return {"status": "skipped", "appended": 0}

        if os.path.isfile(RAG_INDEX_PATH):
            try:
                index = joblib.load(RAG_INDEX_PATH)
            except Exception:
                index = None
        else:
            index = None

        if index is None:
            vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=1)
            texts = [r["_rag_text"] for r in new_reviews]
            matrix = vectorizer.fit_transform(texts)
            index = {
                "version": 1,
                "records": new_reviews,
                "vectorizer": vectorizer,
                "tfidf_matrix": matrix,
                "meta": {
                    "indexed_records": len(new_reviews),
                    "source_stats": {"training_data": len(new_reviews)},
                },
            }
            appended = len(new_reviews)
        else:
            existing = index.get("records", [])
            vectorizer = index.get("vectorizer")
            matrix = index.get("tfidf_matrix")
            seen = {r["_rag_text"][:200].lower() for r in existing}
            to_add = [r for r in new_reviews if r["_rag_text"][:200].lower() not in seen]
            if not to_add or vectorizer is None:
                return {"status": "skipped", "appended": 0}
            new_matrix = vectorizer.transform([r["_rag_text"] for r in to_add])
            existing.extend(to_add)
            matrix = vstack([matrix, new_matrix]) if matrix is not None else new_matrix
            index["records"] = existing
            index["tfidf_matrix"] = matrix
            meta = index.setdefault("meta", {})
            meta["indexed_records"] = len(existing)
            stats = meta.setdefault("source_stats", {})
            stats["training_data"] = stats.get("training_data", 0) + len(to_add)
            appended = len(to_add)

        joblib.dump(index, RAG_INDEX_PATH, compress=3)

        try:
            from app.services.rag_service import RagService
            RagService.reload_index()
        except Exception:
            logging.getLogger(__name__).debug("update_rag_index: hata yutuldu", exc_info=True)

        return {"status": "success", "appended": appended, "total_indexed": index["meta"]["indexed_records"]}

    def get_training_stats(self) -> dict[str, Any]:
        """Sample counts per category, sentiment, domain."""
        reviews = _read_jsonl(REVIEWS_JSONL)
        corrections = _read_jsonl(CORRECTIONS_JSONL)
        dialogues = _read_jsonl(CHATBOT_JSONL)
        meta = _load_meta()

        category_counts: dict[str, int] = {}
        sentiment_counts: dict[str, int] = {}
        domain_counts: dict[str, int] = {}

        for row in reviews + corrections:
            cat = row.get("category") or row.get("correct_category", "Diğer")
            sent = row.get("sentiment") or row.get("correct_sentiment", "Neutral")
            src = row.get("source", "manual")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1
            domain_counts[src] = domain_counts.get(src, 0) + 1

        return {
            "incremental_reviews": len(reviews),
            "corrections": len(corrections),
            "chatbot_dialogues": len(dialogues),
            "total_samples": len(reviews) + len(corrections),
            "category_distribution": [
                {"category": k, "count": v} for k, v in sorted(category_counts.items(), key=lambda x: -x[1])
            ],
            "sentiment_distribution": [
                {"sentiment": k, "count": v} for k, v in sorted(sentiment_counts.items(), key=lambda x: -x[1])
            ],
            "domain_distribution": domain_counts,
            "last_retrain": meta.get("last_retrain"),
            "accuracy_before": meta.get("accuracy_before"),
            "accuracy_after": meta.get("accuracy_after"),
            "f1_after": meta.get("f1_after"),
            "total_retrains": meta.get("total_retrains", 0),
            "paths": {
                "reviews": REVIEWS_JSONL,
                "corrections": CORRECTIONS_JSONL,
                "chatbot": CHATBOT_JSONL,
            },
        }

    def export_training_data(self) -> dict[str, Any]:
        """Export full training set for download."""
        return {
            "reviews": _read_jsonl(REVIEWS_JSONL),
            "corrections": _read_jsonl(CORRECTIONS_JSONL),
            "chatbot_dialogues": _read_jsonl(CHATBOT_JSONL),
            "stats": self.get_training_stats(),
        }

    def process_feedback_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Process a learning_store feedback record into training samples."""
        comment = record.get("comment", "")
        labels = record.get("user_labels") or {}
        ai_pred = record.get("ai_prediction") or {}
        review_id = record.get("review_id", "")
        rating = record.get("rating")
        source = record.get("source", "manual")

        if record.get("accepted") is True:
            sample = self.add_training_sample(
                review=comment,
                labels=labels,
                ai_prediction=ai_pred,
                rating=rating,
                source=source,
                weight=1,
                review_id=review_id,
            )
            keywords = labels.get("keywords") or []
            if keywords:
                sentiment = (labels.get("sentiment") or "").lower()
                key = "positive_phrases" if sentiment == "positive" else "negative_phrases"
                self.retrain_sentiment_lexicon({key: keywords})
            return {"action": "accepted", "sample": sample}

        if record.get("accepted") is False and record.get("correction"):
            corr = record["correction"]
            sample = self.add_correction_sample(
                review_id=review_id,
                comment=comment,
                correct_category=corr.get("category") or labels.get("category", "Diğer"),
                correct_sentiment=corr.get("sentiment") or labels.get("sentiment", "Neutral"),
                keywords=corr.get("keywords") or labels.get("keywords"),
            )
            return {"action": "corrected", "sample": sample}

        return {"action": "pending"}


_trainer: Optional[IncrementalTrainer] = None


def get_incremental_trainer() -> IncrementalTrainer:
    global _trainer
    if _trainer is None:
        _trainer = IncrementalTrainer()
    return _trainer
