"""
Çok platformlu otel yorumu içe aktarma şeması ve analiz pipeline entegrasyonu.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_service")


class ReviewAnalysisResult(BaseModel):
    """Tam analiz pipeline çıktısı."""
    department: str = ""
    aspect: str = ""
    sentiment: str = "Neutral"
    urgency: str = "low"
    need_action: bool = False
    suggested_response: str = ""
    action_item: str = ""
    absa_aspects: list[dict[str, Any]] = Field(default_factory=list)
    # Ek pipeline alanları
    sentiment_score: float = 0.0
    category: str = ""
    confidence: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    summary: str = ""
    satisfaction_level: str = ""
    translated_comment: str = ""
    detected_language: str = ""


class IngestedReview(BaseModel):
    """Zengin yorum kaydı — tüm platformlardan birleşik şema."""
    hotel: str = ""
    country: str = ""
    city: str = ""
    language: str = ""
    platform: str = ""
    date: str = ""
    rating: float = 0.0
    title: str = ""
    comment: str = ""
    traveler_type: str = ""
    room_type: str = ""
    stay_duration: str = ""
    trip_purpose: str = ""
    positive_text: str = ""
    negative_text: str = ""
    guest_name: str = "Anonim"
    helpful_count: int = 0
    is_most_helpful: bool = False
    review_id: str = ""
    analysis: ReviewAnalysisResult = Field(default_factory=ReviewAnalysisResult)
    comment_hash: str = ""
    source_url: str = ""
    ingestion_method: str = ""
    legal_notice: str = ""

    model_config = {"extra": "ignore"}

    def compute_hash(self) -> str:
        """Yorum metninden dedup hash üret."""
        normalized = (self.comment or "").strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def ensure_hash(self) -> "IngestedReview":
        if not self.comment_hash:
            self.comment_hash = self.compute_hash()
        return self

    def to_legacy_dict(self) -> dict[str, Any]:
        """Eski ScraperService uyumluluğu."""
        return {
            "guest_name": self.guest_name,
            "comment": self.comment,
            "rating": int(round(self.rating)) if self.rating else None,
            "source": self.platform,
            "review_date": self.date,
            "title": self.title,
            "language": self.language,
            "hotel": self.hotel,
            "country": self.country,
            "city": self.city,
        }

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["analysis"] = self.analysis.model_dump()
        d["helpful_count"] = self.helpful_count
        d["is_most_helpful"] = self.is_most_helpful
        return d

    def to_analysis_pipeline(
        self,
        api_key: Optional[str] = None,
        store: bool = True,
    ) -> "IngestedReview":
        """
        Tam analiz pipeline:
        Çeviri → Sentiment → Kategori → ABSA → Memnuniyet → Departman → Yanıt → Aksiyon
        """
        from app.services.translation_service import TranslationService
        from app.services.sentiment_service import SentimentService
        from app.services.category_service import CategoryService
        from app.services.keyword_service import KeywordService
        from app.services.rag_service import RagService
        from app.services.absa_service import AbsaService, split_clauses_absa
        from app.services.satisfaction_scale import resolve_satisfaction_label
        from app.services.entity_tracker_service import get_entity_tracker_service

        if not self.comment or not self.comment.strip():
            return self

        rating_int = int(round(self.rating)) if self.rating else None

        # 1. Çeviri
        turkish_comment, detected_lang = TranslationService.translate_to_turkish(
            text=self.comment,
            source_lang=self.language or None,
        )
        if not self.language:
            self.language = detected_lang

        # 2. Sentiment
        is_manipulation = SentimentService.is_manipulation(turkish_comment, rating_int)
        sentiment, sentiment_score = SentimentService.analyze_sentiment(
            text=turkish_comment,
            rating=rating_int,
        )

        # 3. Kategori
        cs = CategoryService()
        category, confidence, _method, secondary_cat, is_mixed = cs.classify_category(
            turkish_comment, api_key, use_gemini=bool(api_key)
        )

        # 4. Anahtar kelimeler
        keywords = KeywordService.extract_keywords(turkish_comment, max_keywords=5)

        # 5. Özet ve öneri
        summary = RagService.generate_summary(turkish_comment)
        suggestion = RagService.generate_suggestion(
            category=category,
            text=turkish_comment,
            keywords=keywords,
            sentiment=sentiment,
            is_mixed=is_mixed,
            secondary_category=secondary_cat,
            is_manipulation=is_manipulation,
        )

        # 6. ABSA
        absa_aspects: list[dict] = []
        department = category
        aspect = category
        urgency = "low"
        need_action = sentiment == "Negative"
        action_item = suggestion if need_action else ""

        if is_mixed or len(split_clauses_absa(turkish_comment)) >= 2:
            absa_result = AbsaService.analyze(turkish_comment, rating=rating_int)
            absa_data = AbsaService.to_dict(absa_result)
            absa_aspects = absa_data.get("aspects", [])
            if absa_aspects:
                primary = absa_aspects[0]
                department = primary.get("department", category)
                aspect = primary.get("aspect", category)
                urgency = primary.get("priority", "low")
                need_action = primary.get("priority") in ("high", "medium") or sentiment == "Negative"
                if primary.get("suggestion"):
                    action_item = primary["suggestion"]

        # 7. Memnuniyet
        satisfaction = resolve_satisfaction_label(sentiment_score, sentiment, rating_int)

        # 8. Yanıt önerisi
        suggested_response = _build_suggested_response(
            sentiment, department, turkish_comment, self.guest_name
        )

        self.analysis = ReviewAnalysisResult(
            department=department,
            aspect=aspect,
            sentiment=sentiment,
            urgency=urgency,
            need_action=need_action,
            suggested_response=suggested_response,
            action_item=action_item,
            absa_aspects=absa_aspects,
            sentiment_score=sentiment_score,
            category=category,
            confidence=confidence,
            keywords=keywords,
            summary=summary,
            satisfaction_level=satisfaction,
            translated_comment=turkish_comment,
            detected_language=detected_lang,
        )

        # 9. Store
        if store:
            try:
                from app.services.review_store import get_review_store
                review_store = get_review_store()
                stored = review_store.add_from_analysis(
                    turkish_comment,
                    rating_int,
                    {
                        "sentiment": sentiment,
                        "sentimentScore": sentiment_score,
                        "category": category,
                        "confidence": confidence,
                        "keywords": keywords,
                        "summary": summary,
                        "suggestion": suggestion,
                        "isMixedReview": is_mixed,
                        "secondaryCategory": secondary_cat,
                        "isManipulation": is_manipulation,
                    },
                    source=self.platform or "ingestion",
                )
                if absa_aspects:
                    review_store.add_absa_aspects(stored.id, absa_aspects)
                entity_tracker = get_entity_tracker_service()
                entity_tracker.register_from_comment(
                    turkish_comment, review_id=stored.id, created_at=stored.created_at
                )
            except Exception as e:
                logger.warning(f"Review store kayıt hatası: {e}")

        return self


def _build_suggested_response(
    sentiment: str,
    department: str,
    comment: str,
    guest_name: str,
) -> str:
    """Misafir yanıt taslağı üret."""
    name = guest_name if guest_name and guest_name != "Anonim" else "Değerli Misafirimiz"
    if sentiment == "Negative":
        return (
            f"Sayın {name}, geri bildiriminiz için teşekkür ederiz. "
            f"{department} departmanımız konuyu inceleyecek ve en kısa sürede size dönüş yapılacaktır."
        )
    if sentiment == "Positive":
        return (
            f"Sayın {name}, olumlu değerlendirmeniz bizleri mutlu etti. "
            f"Sizi tekrar ağırlamayı dört gözle bekliyoruz."
        )
    return f"Sayın {name}, geri bildiriminiz için teşekkür ederiz."


def normalize_rating(value: Any) -> float:
    """Çeşitli rating formatlarını 0-5 aralığına normalize et."""
    if value is None or value == "":
        return 0.0
    try:
        r = float(value)
        if r > 5:
            r = r / 2  # 10'luk skala
        return max(0.0, min(5.0, r))
    except (TypeError, ValueError):
        return 0.0


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
