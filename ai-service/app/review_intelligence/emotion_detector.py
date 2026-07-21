"""Emotion taxonomy — positive/negative branches per clause."""

from __future__ import annotations

import re

from app.review_intelligence.models import EmotionCategory, EmotionInfo, SentimentInfo

_POSITIVE_EMOTIONS: list[tuple[str, EmotionCategory]] = [
    (r"\b(harika|mukemmel|mükemmel|bayildim|bayıldım|super|süper|efsane)\b", EmotionCategory.DELIGHT),
    (r"\b(tesekkur|teşekkür|minnet|memnun)\b", EmotionCategory.GRATITUDE),
    (r"\b(begend|beğend|guzel|güzel|iyi|rahat|temiz|lezzetli)\b", EmotionCategory.SATISFACTION),
]

_NEGATIVE_EMOTIONS: list[tuple[str, EmotionCategory]] = [
    (r"\b(korkt|panik|tehlike|yangin|yangın|alarm|acil)\b", EmotionCategory.FEAR),
    (r"\b(ofke|öfke|sinir|kaba|saygisiz|saygısız)\b", EmotionCategory.ANGER),
    (r"\b(berbat|igrenc|iğrenç|pis|kokuyor|mide)\b", EmotionCategory.DISGUST),
    (r"\b(hayal kirikl|hayal kırıkl|uzgun|üzgün|kotu|kötü|sikayet|şikayet)\b", EmotionCategory.DISAPPOINTMENT),
    (r"\b(bekled|calismiyor|çalışmıyor|bozuk|yine|tekrar|hala|hâlâ)\b", EmotionCategory.FRUSTRATION),
]


class EmotionDetector:
    """Stage 10: Emotion taxonomy with positive/negative branches."""

    def detect(self, clause: str, sentiment: SentimentInfo) -> EmotionInfo:
        text = clause.lower()
        patterns = _NEGATIVE_EMOTIONS if sentiment.label in ("Negative", "Mixed") else _POSITIVE_EMOTIONS
        if sentiment.label == "Neutral":
            patterns = _POSITIVE_EMOTIONS + _NEGATIVE_EMOTIONS

        best: EmotionCategory = EmotionCategory.NEUTRAL
        best_conf = 0.4
        branch = "neutral"

        for pattern, emotion in patterns:
            if re.search(pattern, text):
                conf = 0.75
                if conf > best_conf:
                    best = emotion
                    best_conf = conf
                    branch = "negative" if emotion in (
                        EmotionCategory.FEAR, EmotionCategory.ANGER,
                        EmotionCategory.DISGUST, EmotionCategory.FRUSTRATION,
                        EmotionCategory.DISAPPOINTMENT,
                    ) else "positive"

        if best == EmotionCategory.NEUTRAL and sentiment.label == "Positive":
            best = EmotionCategory.SATISFACTION
            branch = "positive"
            best_conf = 0.6
        elif best == EmotionCategory.NEUTRAL and sentiment.label == "Negative":
            best = EmotionCategory.DISAPPOINTMENT
            branch = "negative"
            best_conf = 0.55

        return EmotionInfo(primary=best, branch=branch, confidence=best_conf)
