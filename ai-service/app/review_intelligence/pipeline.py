"""Review Intelligence pipeline — 14-stage modular orchestrator (NOT single LLM)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.review_intelligence.aspect_extractor import AspectExtractor

logger = logging.getLogger("ai_service.ri_pipeline")
from app.review_intelligence.department_mapper import DepartmentMapper
from app.review_intelligence.emotion_detector import EmotionDetector
from app.review_intelligence.models import (
    AspectInfo,
    ClauseSegment,
    EntityInfo,
    ReviewIntelligenceResult,
    ReviewSummary,
    SeverityLevel,
    TrendSummary,
    UrgencyLevel,
)
from app.review_intelligence.parser import ReviewParser
from app.review_intelligence.recommendation import RecommendationEngine
from app.review_intelligence.root_cause import RootCauseAnalyzer
from app.review_intelligence.sentiment_engine import SentimentEngine
from app.review_intelligence.severity_urgency import SeverityUrgencyScorer

PIPELINE_VERSION = "1.0.0"

_SEVERITY_RANK = {
    SeverityLevel.LOW: 0,
    SeverityLevel.MEDIUM: 1,
    SeverityLevel.HIGH: 2,
    SeverityLevel.CRITICAL: 3,
}

_URGENCY_RANK = {
    UrgencyLevel.ROUTINE: 0,
    UrgencyLevel.NORMAL: 1,
    UrgencyLevel.ELEVATED: 2,
    UrgencyLevel.IMMEDIATE: 3,
    UrgencyLevel.EMERGENCY: 4,
}


class ReviewIntelligencePipeline:
    """
    Modular pipeline stages:
    Raw → Language → Normalization → Sentence → Clause → Entity → Aspect
    → Department → Sentiment → Emotion → Severity → Urgency → Root Cause
    → Action Recommendation → Structured JSON
    """

    def __init__(self) -> None:
        self.parser = ReviewParser()
        self.aspect_extractor = AspectExtractor()
        self.department_mapper = DepartmentMapper(self.aspect_extractor.engine)
        self.sentiment_engine = SentimentEngine()
        self.emotion_detector = EmotionDetector()
        self.severity_scorer = SeverityUrgencyScorer()
        self.root_cause = RootCauseAnalyzer()
        self.recommendation = RecommendationEngine()

    def run(
        self,
        review_text: str,
        review_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        language: str | None = None,
        rating: int | None = None,
    ) -> ReviewIntelligenceResult:
        import time as _time
        _t0 = _time.perf_counter()
        _MAX_MS = 30000  # RI pipeline internal timeout — 30s budget

        def _remaining_ms() -> float:
            return _MAX_MS - (_time.perf_counter() - _t0) * 1000

        parsed = self.parser.parse(review_text, language=language)
        lang = parsed.language

        overall, overall_score, is_mixed = self.sentiment_engine.analyze_document(
            parsed.turkish_text, rating=rating
        )

        segments: list[ClauseSegment] = []
        all_triggers = []
        max_sev = SeverityLevel.LOW
        max_urg = UrgencyLevel.ROUTINE
        dept_counts: dict[str, int] = {}

        # Kalabalık yorumlar için max clause limiti
        _MAX_CLAUSES = 20
        _clauses = parsed.clauses[:_MAX_CLAUSES]
        if len(parsed.clauses) > _MAX_CLAUSES:
            _clauses.append(f"(+{len(parsed.clauses) - _MAX_CLAUSES} cümlecik daha)")

        for idx, clause in enumerate(_clauses):
            # Per-clause deadline: 500ms/clause — aşarsa sonraki clause'ları skip
            if _remaining_ms() < 300:
                logger.debug(f"RI pipeline: clause {idx}/{len(_clauses)} — deadline approaching, skipping remaining")
                break

            entities = self.aspect_extractor.extract_entities(clause, lang=lang)
            aspect_map = self.aspect_extractor.extract_aspect(clause, lang=lang)
            dept = self.department_mapper.map_department(aspect_map, entities)
            sentiment = self.sentiment_engine.analyze_clause(
                clause, parsed.turkish_text, rating
            )
            emotion = self.emotion_detector.detect(clause, sentiment)
            severity, urgency = self.severity_scorer.score(
                clause, sentiment, emotion, dept.key
            )
            root = self.root_cause.analyze(clause, aspect_map.aspect, severity)
            rec = self.recommendation.recommend(
                clause,
                dept.label,
                sentiment.label,
                severity,
                urgency,
                aspect_map.aspect,
            )
            triggers = self.recommendation.workflow_triggers(clause, severity, urgency)
            all_triggers.extend(triggers)
            keywords = clause.split()[:5]

            if _SEVERITY_RANK[severity] > _SEVERITY_RANK[max_sev]:
                max_sev = severity
            if _URGENCY_RANK[urgency] > _URGENCY_RANK[max_urg]:
                max_urg = urgency
            dept_counts[dept.key] = dept_counts.get(dept.key, 0) + 1

            segments.append(ClauseSegment(
                index=idx,
                text=clause,
                entities=[
                    EntityInfo(
                        entity_id=e.entity_id,
                        entity_type=e.entity_type,
                        label=e.label,
                        confidence=e.confidence,
                        matched_term=e.matched_term,
                    )
                    for e in entities
                ],
                aspect=AspectInfo(
                    key=aspect_map.aspect,
                    label=aspect_map.aspect_label,
                    category=aspect_map.category,
                    confidence=aspect_map.confidence,
                    method=aspect_map.method,
                ),
                department=dept,
                sentiment=sentiment,
                emotion=emotion,
                severity=severity,
                urgency=urgency,
                root_cause=root,
                recommendation=rec,
                keywords=keywords,
            ))

        dominant_dept = max(dept_counts, key=dept_counts.get) if dept_counts else None
        trends_data = self.root_cause.get_trends()

        headline = self._build_headline(segments, is_mixed)

        return ReviewIntelligenceResult(
            review_id=review_id,
            pipeline_version=PIPELINE_VERSION,
            language=lang,
            raw_text=review_text,
            normalized_text=parsed.normalized_text,
            sentences=parsed.sentences,
            clauses=parsed.clauses,
            segments=segments,
            summary=ReviewSummary(
                headline=headline,
                overall_sentiment=overall,
                overall_score=overall_score,
                is_mixed=is_mixed,
                clause_count=len(parsed.clauses),
                dominant_department=dominant_dept,
                max_severity=max_sev,
                max_urgency=max_urg,
            ),
            trends=TrendSummary(**trends_data),
            workflow_triggers=all_triggers,
            metadata=metadata or {},
        )

    @staticmethod
    def _build_headline(segments: list[ClauseSegment], is_mixed: bool) -> str:
        if not segments:
            return "Boş yorum"
        neg = [s for s in segments if s.sentiment.label == "Negative"]
        pos = [s for s in segments if s.sentiment.label == "Positive"]
        if is_mixed:
            return f"Karışık yorum: {len(pos)} olumlu, {len(neg)} olumsuz cümlecik"
        if neg:
            return f"Olumsuz: {neg[0].aspect.label}"
        if pos:
            return f"Olumlu: {pos[0].aspect.label}"
        return "Nötr değerlendirme"
