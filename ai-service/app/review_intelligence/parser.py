"""Parser stage — language detection, normalization, sentence/clause segmentation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.translation_service import TranslationService
from app.services.absa_service import split_clauses_absa
from app.services.turkish_nlp_utils import normalize_turkish


@dataclass
class ParseResult:
    language: str
    raw_text: str
    normalized_text: str
    turkish_text: str
    sentences: list[str]
    clauses: list[str]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


class ReviewParser:
    """Stage 1–5: Raw → Language → Normalization → Sentence → Clause."""

    def parse(
        self,
        review_text: str,
        language: str | None = None,
    ) -> ParseResult:
        raw = review_text.strip()
        turkish_text, detected_lang = TranslationService.translate_to_turkish(
            text=raw,
            source_lang=language,
        )
        lang = language or detected_lang or "tr"
        normalized = normalize_turkish(turkish_text)
        sentences = _split_sentences(normalized)
        clauses = split_clauses_absa(normalized)
        if not clauses and normalized:
            clauses = [normalized]

        return ParseResult(
            language=lang,
            raw_text=raw,
            normalized_text=normalized,
            turkish_text=normalized,
            sentences=sentences,
            clauses=clauses,
        )
