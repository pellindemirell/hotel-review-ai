"""
Kalıcı öğrenme geri bildirim deposu — ai-service/data/learning_feedback.json

Her kayıt: review_id, comment, rating, user_labels, ai_prediction, correction,
accepted, feedback_score, timestamp, source.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
FEEDBACK_FILE = os.path.join(_DATA_DIR, "learning_feedback.json")

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _load_all() -> list[dict[str, Any]]:
    _ensure_data_dir()
    if not os.path.isfile(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_all(records: list[dict[str, Any]]) -> None:
    _ensure_data_dir()
    with open(FEEDBACK_FILE, encoding="utf-8", mode="w") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


class LearningStore:
    """CRUD for reinforcement / incremental learning feedback records."""

    def save_prediction(
        self,
        review_id: str,
        comment: str,
        rating: Optional[int],
        ai_prediction: dict[str, Any],
        source: str = "manual",
        keywords: Optional[list] = None,
        aspects: Optional[list] = None,
    ) -> dict[str, Any]:
        """Store AI prediction pending user feedback."""
        with _lock:
            records = _load_all()
            existing = next((r for r in records if r.get("review_id") == review_id), None)
            user_labels = {
                "sentiment": ai_prediction.get("sentiment", "Neutral"),
                "category": ai_prediction.get("category", "Diğer"),
                "keywords": keywords or ai_prediction.get("keywords") or [],
                "aspects": aspects or [],
            }
            if existing:
                existing.update({
                    "comment": comment,
                    "rating": rating,
                    "user_labels": user_labels,
                    "ai_prediction": ai_prediction,
                    "source": source,
                    "timestamp": _utc_now(),
                })
                record = existing
            else:
                record = {
                    "review_id": review_id,
                    "comment": comment,
                    "rating": rating,
                    "user_labels": user_labels,
                    "ai_prediction": ai_prediction,
                    "correction": None,
                    "accepted": None,
                    "feedback_score": 0.0,
                    "timestamp": _utc_now(),
                    "source": source,
                }
                records.append(record)
            _save_all(records)
            return dict(record)

    def submit_feedback(
        self,
        review_id: str,
        accepted: bool,
        comment: str = "",
        corrections: Optional[dict[str, Any]] = None,
        source: str = "manual",
    ) -> dict[str, Any]:
        """User accepts or corrects a prediction."""
        with _lock:
            records = _load_all()
            record = next((r for r in records if r.get("review_id") == review_id), None)
            if not record and comment:
                record = {
                    "review_id": review_id or str(uuid.uuid4())[:8],
                    "comment": comment,
                    "rating": None,
                    "user_labels": {},
                    "ai_prediction": {},
                    "correction": None,
                    "accepted": None,
                    "feedback_score": 0.0,
                    "timestamp": _utc_now(),
                    "source": source,
                }
                records.append(record)
            if not record:
                raise ValueError(f"Kayıt bulunamadı: {review_id}")

            if comment:
                record["comment"] = comment
            record["accepted"] = accepted
            record["timestamp"] = _utc_now()

            if accepted:
                record["correction"] = None
                record["feedback_score"] = 1.0
                pred = record.get("ai_prediction") or {}
                record["user_labels"] = {
                    "sentiment": pred.get("sentiment", "Neutral"),
                    "category": pred.get("category", "Diğer"),
                    "keywords": pred.get("keywords") or record.get("user_labels", {}).get("keywords", []),
                    "aspects": record.get("user_labels", {}).get("aspects", []),
                }
            elif corrections:
                record["correction"] = dict(corrections)
                record["feedback_score"] = 0.0
                ul = dict(record.get("user_labels") or {})
                if corrections.get("sentiment"):
                    ul["sentiment"] = corrections["sentiment"]
                if corrections.get("category"):
                    ul["category"] = corrections["category"]
                if corrections.get("keywords") is not None:
                    ul["keywords"] = corrections["keywords"]
                if corrections.get("aspects") is not None:
                    ul["aspects"] = corrections["aspects"]
                record["user_labels"] = ul

            _save_all(records)
            return dict(record)

    def save_chat_feedback(
        self,
        query: str,
        answer: str,
        accepted: bool,
        correction: Optional[str] = None,
        intent: str = "",
        mode: str = "chat",
    ) -> dict[str, Any]:
        """Chatbot Q&A correction record."""
        review_id = f"chat-{hash(query + answer) & 0xFFFFFF:06x}"
        with _lock:
            records = _load_all()
            record = {
                "review_id": review_id,
                "comment": query,
                "rating": None,
                "user_labels": {"answer": answer, "intent": intent},
                "ai_prediction": {"answer": answer, "mode": mode},
                "correction": {"answer": correction} if correction else None,
                "accepted": accepted,
                "feedback_score": 1.0 if accepted else 0.0,
                "timestamp": _utc_now(),
                "source": "chat",
            }
            records.append(record)
            _save_all(records)
            return record

    def get_by_review_id(self, review_id: str) -> Optional[dict[str, Any]]:
        return next((r for r in _load_all() if r.get("review_id") == review_id), None)

    def list_all(self, limit: Optional[int] = None, source: Optional[str] = None) -> list[dict[str, Any]]:
        rows = _load_all()
        if source:
            rows = [r for r in rows if r.get("source") == source]
        if limit:
            return rows[-limit:]
        return rows

    def count(self) -> int:
        return len(_load_all())

    def get_stats(self) -> dict[str, Any]:
        records = _load_all()
        accepted = sum(1 for r in records if r.get("accepted") is True)
        corrected = sum(1 for r in records if r.get("accepted") is False)
        pending = sum(1 for r in records if r.get("accepted") is None)

        category_dist: dict[str, int] = {}
        sentiment_dist: dict[str, int] = {}
        source_dist: dict[str, int] = {}
        for r in records:
            src = r.get("source", "unknown")
            source_dist[src] = source_dist.get(src, 0) + 1
            labels = r.get("user_labels") or {}
            if r.get("correction"):
                labels = {**labels, **{k: v for k, v in r["correction"].items() if k in ("category", "sentiment")}}
            cat = labels.get("category") or (r.get("ai_prediction") or {}).get("category", "Diğer")
            sent = labels.get("sentiment") or (r.get("ai_prediction") or {}).get("sentiment", "Neutral")
            category_dist[cat] = category_dist.get(cat, 0) + 1
            sentiment_dist[sent] = sentiment_dist.get(sent, 0) + 1

        return {
            "total": len(records),
            "accepted": accepted,
            "corrected": corrected,
            "pending": pending,
            "category_distribution": [
                {"category": k, "count": v} for k, v in sorted(category_dist.items(), key=lambda x: -x[1])
            ],
            "sentiment_distribution": [
                {"sentiment": k, "count": v} for k, v in sorted(sentiment_dist.items(), key=lambda x: -x[1])
            ],
            "source_distribution": source_dist,
        }

    def export_training_records(self) -> list[dict[str, Any]]:
        """Export confirmed labels for training."""
        out = []
        for r in _load_all():
            if r.get("accepted") is None:
                continue
            labels = r.get("user_labels") or {}
            out.append({
                "review_id": r.get("review_id"),
                "comment": r.get("comment", ""),
                "rating": r.get("rating"),
                "category": labels.get("category", "Diğer"),
                "sentiment": labels.get("sentiment", "Neutral"),
                "keywords": labels.get("keywords", []),
                "accepted": r.get("accepted"),
                "weight": 3 if r.get("accepted") is False else 1,
                "source": r.get("source", "manual"),
                "timestamp": r.get("timestamp"),
            })
        return out

    def clear(self) -> None:
        with _lock:
            _save_all([])


_store: Optional[LearningStore] = None


def get_learning_store() -> LearningStore:
    global _store
    if _store is None:
        _store = LearningStore()
    return _store
