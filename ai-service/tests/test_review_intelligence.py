"""Tests for Review Intelligence Engine — DOC-004 acceptance scenarios."""

from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.review_intelligence import ReviewIntelligenceService
from app.review_intelligence.models import SeverityLevel, UrgencyLevel
from app.services.absa_service import split_clauses_absa


@pytest.fixture
def service() -> ReviewIntelligenceService:
    return ReviewIntelligenceService()


FOUR_CLAUSE_REVIEW = (
    "Oda temizdi ama klima çalışmıyordu. "
    "Yemekleri çok beğendik fakat kahvaltıda çeşit azdı."
)

MIXED_ASPECT_REVIEW = "Oda güzeldi ama banyo berbattı."

FIRE_ALARM_REVIEW = "Gece yangın alarmı çaldı, herkes panik oldu, itfaiye geldi."


def test_four_clause_segmentation(service: ReviewIntelligenceService):
    """User example: 4 operational clauses from Turkish mixed review."""
    clauses = split_clauses_absa(FOUR_CLAUSE_REVIEW)
    assert len(clauses) == 4, f"Beklenen 4 cümlecik, alınan: {clauses}"

    result = service.analyze(FOUR_CLAUSE_REVIEW, review_id="test-4clause")
    assert len(result.clauses) == 4
    assert len(result.segments) == 4
    assert result.summary.clause_count == 4


def test_mixed_aspect_sentiment(service: ReviewIntelligenceService):
    """User example: oda positive, banyo negative — aspect-based not document-level."""
    result = service.analyze(MIXED_ASPECT_REVIEW)
    assert result.summary.is_mixed is True
    assert result.summary.overall_sentiment == "Mixed"

    sentiments = {s.aspect.key: s.sentiment.label for s in result.segments}
    texts = {s.text.lower(): s.sentiment.label for s in result.segments}

    pos_segments = [s for s in result.segments if s.sentiment.label == "Positive"]
    neg_segments = [s for s in result.segments if s.sentiment.label == "Negative"]
    assert len(pos_segments) >= 1, "En az bir olumlu segment bekleniyor"
    assert len(neg_segments) >= 1, "En az bir olumsuz segment bekleniyor"

    room_seg = next((s for s in result.segments if "oda" in s.text.lower() and "banyo" not in s.text.lower()), None)
    bath_seg = next((s for s in result.segments if "banyo" in s.text.lower()), None)
    if room_seg:
        assert room_seg.sentiment.label == "Positive"
    if bath_seg:
        assert bath_seg.sentiment.label == "Negative"


def test_fire_alarm_critical_emergency(service: ReviewIntelligenceService):
    """User example: yangın alarmı → Critical severity + Emergency urgency."""
    result = service.analyze(FIRE_ALARM_REVIEW)
    assert result.summary.max_severity == SeverityLevel.CRITICAL
    assert result.summary.max_urgency == UrgencyLevel.EMERGENCY
    assert len(result.workflow_triggers) >= 1
    trigger_types = {t.trigger_type for t in result.workflow_triggers}
    assert "incident" in trigger_types or "notify_security" in trigger_types


def test_full_json_structure(service: ReviewIntelligenceService):
    """Validate complete JSON structure against DOC-004 schema fields."""
    result = service.analyze(FOUR_CLAUSE_REVIEW, review_id="json-test", metadata={"hotel": "demo"})
    data = result.to_dict()

    required_top = {
        "review_id", "pipeline_version", "language", "raw_text", "normalized_text",
        "sentences", "clauses", "segments", "summary", "trends",
        "workflow_triggers", "metadata", "processed_at",
    }
    assert required_top.issubset(data.keys())

    assert data["pipeline_version"] == "1.0.0"
    assert data["review_id"] == "json-test"
    assert isinstance(data["segments"], list) and len(data["segments"]) > 0

    seg = data["segments"][0]
    seg_fields = {
        "index", "text", "entities", "aspect", "department",
        "sentiment", "emotion", "severity", "urgency",
        "root_cause", "recommendation", "keywords",
    }
    assert seg_fields.issubset(seg.keys())

    summary = data["summary"]
    assert "overall_sentiment" in summary
    assert "is_mixed" in summary
    assert "max_severity" in summary
    assert "max_urgency" in summary

    # JSON serializable
    json.dumps(data, ensure_ascii=False)


def test_analyze_batch(service: ReviewIntelligenceService):
    reviews = [MIXED_ASPECT_REVIEW, FIRE_ALARM_REVIEW]
    results = service.analyze_batch(reviews)
    assert len(results) == 2
    assert results[0].summary.is_mixed is True
    assert results[1].summary.max_urgency == UrgencyLevel.EMERGENCY


def test_department_mapping_present(service: ReviewIntelligenceService):
    result = service.analyze("Klima çalışmıyordu, oda çok sıcaktı.")
    hvac_segments = [
        s for s in result.segments
        if s.department.key.startswith("engineering") or "klima" in s.text.lower()
    ]
    assert len(hvac_segments) >= 1
    assert hvac_segments[0].department.key != "genel"


def test_recommendation_generated(service: ReviewIntelligenceService):
    result = service.analyze("Banyo berbattı, tuvalet temiz değildi.")
    for seg in result.segments:
        if seg.sentiment.label == "Negative":
            assert seg.recommendation is not None
            assert len(seg.recommendation.action) > 0
