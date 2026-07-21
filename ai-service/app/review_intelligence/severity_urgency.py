"""Severity and urgency scoring — distinct dimensions per DOC-004."""

from __future__ import annotations

import re

from app.review_intelligence.models import (
    EmotionInfo,
    SentimentInfo,
    SeverityLevel,
    UrgencyLevel,
)

# Critical / emergency triggers
_EMERGENCY_PATTERNS = (
    r"\b(yangin|yangın|fire|duman|smoke|patlama|explosion)\b",
    r"\b(gas\s*leak|gaz\s*kaça|gaz\s*kac|zehirlenme|poison)\b",
    r"\b(yangin\s*alarm|yangın\s*alarm|itfaiye|112|110)\b",
)

_CRITICAL_PATTERNS = (
    r"\b(elektrik\s*carp|elektrik\s*çarp|su\s*baskin|su\s*baskın|sel)\b",
    r"\b(hirsiz|hırsız|silah|saldiri|saldırı|tecavuz)\b",
    r"\b(kilit\s*acilm|kilit\s*açılm|kapi\s*acilm|kapı\s*açılm)\b",
)

_HIGH_PATTERNS = (
    r"\b(klima\s*calism|klima\s*çalış|klima\s*bozuk|asansor\s*takil|asansör\s*takıl)\b",
    r"\b(sicak\s*su\s*yok|sıcak\s*su\s*yok|wifi\s*yok|internet\s*yok)\b",
    r"\b(böcek|fare|hamam\s*bocegi|hamam\s*böceği|kene)\b",
)

_MEDIUM_PATTERNS = (
    r"\b(kirli|pis|leke|kokuyor|gurultu|gürültü|yavas|yavaş)\b",
    r"\b(ilgisiz|kaba|bekled|gec\s*gel|geç\s*gel)\b",
)


class SeverityUrgencyScorer:
    """Stage 11–12: Severity (impact) vs Urgency (time sensitivity)."""

    def score(
        self,
        clause: str,
        sentiment: SentimentInfo,
        emotion: EmotionInfo,
        department_key: str,
    ) -> tuple[SeverityLevel, UrgencyLevel]:
        text = clause.lower()

        # Emergency: life/safety — yangın alarmı örneği
        if any(re.search(p, text) for p in _EMERGENCY_PATTERNS):
            return SeverityLevel.CRITICAL, UrgencyLevel.EMERGENCY

        if any(re.search(p, text) for p in _CRITICAL_PATTERNS):
            return SeverityLevel.CRITICAL, UrgencyLevel.IMMEDIATE

        if emotion.primary.value == "fear":
            return SeverityLevel.CRITICAL, UrgencyLevel.IMMEDIATE

        if any(re.search(p, text) for p in _HIGH_PATTERNS):
            sev = SeverityLevel.HIGH
            urg = UrgencyLevel.ELEVATED
            if department_key.startswith("engineering"):
                urg = UrgencyLevel.IMMEDIATE
            return sev, urg

        if sentiment.label == "Negative":
            if any(re.search(p, text) for p in _MEDIUM_PATTERNS):
                return SeverityLevel.MEDIUM, UrgencyLevel.NORMAL
            if abs(sentiment.score) >= 0.7:
                return SeverityLevel.MEDIUM, UrgencyLevel.NORMAL
            return SeverityLevel.LOW, UrgencyLevel.ROUTINE

        return SeverityLevel.LOW, UrgencyLevel.ROUTINE
