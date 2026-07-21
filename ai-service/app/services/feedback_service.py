"""
Kullanıcı geri bildirimi ve düzeltme servisi.
learning_store + incremental_trainer ile reinforcement learning.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.learning_store import get_learning_store
from app.services.incremental_trainer import get_incremental_trainer
from app.services.learning_service import CORRECTION_WEIGHT, get_learning_service
from app.services.review_store import get_review_store


class FeedbackService:
    def __init__(self) -> None:
        self._store = get_learning_store()
        self._trainer = get_incremental_trainer()
        self._learning = get_learning_service()
        self._review_store = get_review_store()

    def _resolve_comment_and_prediction(
        self, review_id: str, comment: str = ""
    ) -> tuple[str, dict[str, Any]]:
        predicted = {}
        resolved_comment = comment

        for r in self._review_store.all_reviews():
            if r.id == review_id:
                resolved_comment = resolved_comment or r.comment
                predicted = {
                    "sentiment": r.sentiment,
                    "category": r.category,
                    "confidence": r.confidence,
                    "keywords": getattr(r, "keywords", []) or [],
                }
                break

        if not resolved_comment:
            fb = self._store.get_by_review_id(review_id)
            if fb:
                resolved_comment = fb.get("comment", "")
                predicted = fb.get("ai_prediction") or predicted
            else:
                recent = self._learning.get_recent_buffer(limit=50)
                for row in recent:
                    if row.get("id") == review_id:
                        resolved_comment = row.get("comment", "")
                        predicted = {
                            "sentiment": row.get("sentiment", ""),
                            "category": row.get("category", ""),
                            "confidence": row.get("confidence", 0.0),
                            "keywords": row.get("keywords", []),
                        }
                        break

        return resolved_comment, predicted

    def submit_feedback(
        self,
        review_id: str,
        accepted: bool,
        comment: str = "",
        corrections: Optional[dict[str, Any]] = None,
        source: str = "manual",
        trigger_retrain: bool = False,
    ) -> dict[str, Any]:
        """Unified feedback — accept or correct."""
        resolved_comment, predicted = self._resolve_comment_and_prediction(review_id, comment)

        if not predicted and resolved_comment:
            predicted = self._store.get_by_review_id(review_id)
            if predicted:
                predicted = predicted.get("ai_prediction") or {}

        record = self._store.submit_feedback(
            review_id=review_id,
            accepted=accepted,
            comment=resolved_comment,
            corrections=corrections,
            source=source,
        )

        train_result = self._trainer.process_feedback_record(record)

        if accepted:
            self._learning.record_from_analysis(
                review_id=review_id,
                comment=resolved_comment,
                rating=record.get("rating"),
                analysis={
                    "sentiment": record["user_labels"].get("sentiment", "Neutral"),
                    "sentimentScore": 0.0,
                    "category": record["user_labels"].get("category", "Diğer"),
                    "confidence": predicted.get("confidence", 1.0),
                    "keywords": record["user_labels"].get("keywords", []),
                },
                source=f"accepted_{source}",
            )
        else:
            corr = corrections or {}
            self._learning.record_correction(
                review_id=review_id,
                correct_category=corr.get("category") or record["user_labels"].get("category", "Diğer"),
                correct_sentiment=corr.get("sentiment") or record["user_labels"].get("sentiment", "Neutral"),
                notes=corr.get("notes", ""),
                comment=resolved_comment,
            )

        retrain_result = None
        if trigger_retrain or (not accepted and self._learning.get_buffer_size() >= 5):
            retrain_result = self._learning.run_retrain(force=not accepted)

        rag_result = self._trainer.update_rag_index([
            {
                "_rag_text": resolved_comment,
                "category": record["user_labels"].get("category", "Diğer"),
                "rating": record.get("rating") if record.get("rating") is not None else "N/A",
                "sentiment": record["user_labels"].get("sentiment", ""),
                "source": f"feedback:{source}",
                "_origin": "learning_feedback",
                "department": record["user_labels"].get("category", ""),
            }
        ]) if resolved_comment else {"appended": 0}

        evaluation = self._learning.evaluate_prediction(
            predicted_category=predicted.get("category", ""),
            predicted_sentiment=predicted.get("sentiment", ""),
            confidence=float(predicted.get("confidence", 0.0)),
            correct_category=record["user_labels"].get("category") if not accepted else None,
            correct_sentiment=record["user_labels"].get("sentiment") if not accepted else None,
        )

        return {
            "status": "ok",
            "review_id": review_id,
            "accepted": accepted,
            "weight": CORRECTION_WEIGHT if not accepted else 1,
            "evaluation": evaluation,
            "train_action": train_result.get("action"),
            "rag_appended": rag_result.get("appended", 0),
            "retrain": retrain_result,
            "message": (
                "Tahmin doğrulandı — eğitim verisine eklendi"
                if accepted
                else f"Düzeltme kaydedildi ({CORRECTION_WEIGHT}x ağırlık)"
            ),
        }

    def submit_correction(
        self,
        review_id: str,
        correct_category: str,
        correct_sentiment: str,
        notes: str = "",
        keywords: Optional[list] = None,
    ) -> dict[str, Any]:
        """Legacy /learn/feedback uyumluluğu."""
        return self.submit_feedback(
            review_id=review_id,
            accepted=False,
            corrections={
                "category": correct_category,
                "sentiment": correct_sentiment,
                "keywords": keywords or [],
                "notes": notes,
            },
            trigger_retrain=False,
        )

    def submit_chat_feedback(
        self,
        query: str,
        answer: str,
        accepted: bool,
        correction: Optional[str] = None,
        intent: str = "",
        mode: str = "chat",
    ) -> dict[str, Any]:
        """Chatbot Q&A geri bildirimi."""
        self._store.save_chat_feedback(query, answer, accepted, correction, intent, mode)
        dialogue = self._trainer.add_chat_dialogue(query, answer, accepted, correction, intent, mode)
        if not accepted and correction:
            self._trainer.update_rag_index([{
                "_rag_text": f"S: {query} C: {correction}",
                "category": "Otel Operasyonları",
                "rating": "N/A",
                "sentiment": "",
                "source": "chat_correction",
                "_origin": "chatbot_dialogues",
                "department": intent or "Front Office",
            }])
        return {"status": "ok", "dialogue_id": dialogue.get("stored_at"), "accepted": accepted}

    def get_accuracy_tracking(self) -> dict[str, Any]:
        stats = self._learning.get_stats()
        trainer_stats = self._trainer.get_training_stats()
        store_stats = self._store.get_stats()
        return {
            "accuracy_before_last_retrain": stats.get("accuracy_before"),
            "accuracy_after_last_retrain": stats.get("accuracy_after"),
            "total_retrains": stats.get("total_retrains", 0),
            "corrections_count": store_stats.get("corrected", 0),
            "accepted_count": store_stats.get("accepted", 0),
            "last_retrain": trainer_stats.get("last_retrain") or stats.get("last_retrain"),
            "training_samples": trainer_stats.get("total_samples", 0),
        }


_service: Optional[FeedbackService] = None


def get_feedback_service() -> FeedbackService:
    global _service
    if _service is None:
        _service = FeedbackService()
    return _service
