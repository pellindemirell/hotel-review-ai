"""Tests for HotelOntologyEngine — DOC-002 acceptance scenarios."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure ai-service app is importable
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.ontology.engine import HotelOntologyEngine
from app.services.ontology_service import OntologyService


@pytest.fixture
def engine() -> HotelOntologyEngine:
    return HotelOntologyEngine()


REVIEW_TEXT = "Oda tertemizdi ama klima çok ses yapıyordu. Yemekler güzeldi."


def test_review_three_segments(engine: HotelOntologyEngine):
    """TS-001: Turkish review splits into 3 segments."""
    segments = engine.parse_review_segments(REVIEW_TEXT)
    assert len(segments) == 3
    texts = [s.text for s in segments]
    assert any("tertemiz" in t.lower() or "oda" in t.lower() for t in texts)
    assert any("klima" in t.lower() or "ses" in t.lower() for t in texts)
    assert any("yemek" in t.lower() for t in texts)


def test_review_segment_aspects(engine: HotelOntologyEngine):
    """TS-001 extended: each segment maps to expected aspect category."""
    segments = engine.parse_review_segments(REVIEW_TEXT)
    aspects = {s.aspect for s in segments}
    assert "room_cleanliness" in aspects
    assert "hvac_noise" in aspects
    assert "food_quality" in aspects


def test_review_segment_sentiments(engine: HotelOntologyEngine):
    segments = engine.parse_review_segments(REVIEW_TEXT)
    by_aspect = {s.aspect: s.sentiment for s in segments}
    assert by_aspect.get("room_cleanliness") == "positive"
    assert by_aspect.get("hvac_noise") == "negative"
    assert by_aspect.get("food_quality") == "positive"


def test_tr_synonym_klima(engine: HotelOntologyEngine):
    """TS-002: Turkish 'klima' resolves to air conditioner entity."""
    ref = engine.resolve_term("klima", lang="tr")
    assert ref.entity_id == "eq_air_conditioner"
    assert ref.confidence >= 0.85


def test_en_synonym_ac(engine: HotelOntologyEngine):
    """TS-003: English 'AC' resolves to same entity."""
    ref = engine.resolve_term("AC", lang="en")
    assert ref.entity_id == "eq_air_conditioner"
    assert ref.confidence >= 0.85


def test_hvac_synonyms_same_entity(engine: HotelOntologyEngine):
    """TS-004: klima / AC / HVAC → same entity_id."""
    terms = [
        ("klima", "tr"),
        ("AC", "en"),
        ("HVAC", "en"),
        ("air conditioner", "en"),
    ]
    ids = {engine.resolve_term(t, lang=lang).entity_id for t, lang in terms}
    assert ids == {"eq_air_conditioner"}


def test_en_aspect_air_conditioner(engine: HotelOntologyEngine):
    """TS-005: English 'Air Conditioner' maps to Engineering/HVAC."""
    mapping = engine.map_aspect("Air Conditioner is too noisy", lang="en")
    assert mapping.department == "engineering_hvac"
    assert mapping.category == "HVAC"
    assert mapping.confidence >= 0.5


def test_responsible_department_hvac(engine: HotelOntologyEngine):
    """TS-006: eq_air_conditioner → engineering_hvac."""
    dept = engine.get_responsible_department("eq_air_conditioner")
    assert dept == "engineering_hvac"


def test_runtime_synonym(engine: HotelOntologyEngine):
    """TS-007: add_synonym works at runtime."""
    engine.add_synonym("eq_air_conditioner", "AC unit", lang="en")
    ref = engine.resolve_term("AC unit", lang="en")
    assert ref.entity_id == "eq_air_conditioner"


def test_ontology_service_adapter_review():
    """TS-010: OntologyService.parse_hotel_review returns dict list."""
    segments = OntologyService.parse_hotel_review(REVIEW_TEXT)
    assert len(segments) == 3
    assert all("text" in s and "aspect" in s for s in segments)


def test_ontology_service_adapter_term():
    ref = OntologyService.resolve_hotel_term("klima", lang="tr")
    assert ref["entity_id"] == "eq_air_conditioner"


def test_engine_stats_gap_reporting(engine: HotelOntologyEngine):
    """Verify v1 seed counts are in expected range."""
    stats = engine.stats()
    assert stats["equipment"] >= 60
    assert stats["human"] >= 20
    assert stats["aspects"] >= 100
    assert stats["responsibilities"] >= 35
