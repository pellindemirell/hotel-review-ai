from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.process_health import ProcessHealthScoreEngine
from app.operational_intelligence.models import AtomicOperationalFact, FactType, SeverityLevel


def _fact(fact_type: FactType, dept: str = "", sub: str = "", sev: SeverityLevel = SeverityLevel.INFO):
    return AtomicOperationalFact(
        fact_id=f"f_{os.urandom(4).hex()}",
        fact_type=fact_type,
        label="test",
        description="test fact",
        evidence=[],
        confidence=0.9,
        department=dept,
        sub_process=sub,
        severity=sev,
    )


class TestHealthScores:
    def test_negative_reviews_lower_score(self):
        engine = ProcessHealthScoreEngine()
        engine.update([
            _fact(FactType.PROCESS_FAILURE, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.CRITICAL),
        ])
        scores = engine.compute()
        assert scores["Kat Hizmetleri"]["overall_health"] < 100

    def test_positive_reviews_high_score(self):
        engine = ProcessHealthScoreEngine()
        engine.update([
            _fact(FactType.OBSERVATION, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.INFO),
        ])
        assert engine.compute()["Kat Hizmetleri"]["overall_health"] >= 90

    def test_score_bounds(self):
        engine = ProcessHealthScoreEngine()
        engine.update([
            _fact(FactType.PROCESS_FAILURE, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.CRITICAL),
        ])
        for data in engine.compute().values():
            assert 0 <= data["overall_health"] <= 100


class TestSubProcesses:
    def test_sub_process_breakdown(self):
        engine = ProcessHealthScoreEngine()
        engine.update([
            _fact(FactType.PROCESS_FAILURE, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.HIGH),
        ])
        subs = engine.compute()["Kat Hizmetleri"]["sub_processes"]
        assert len(subs) > 0

    def test_severity_weights(self):
        critical = ProcessHealthScoreEngine()
        critical.update([_fact(FactType.PROCESS_FAILURE, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.CRITICAL)])

        low = ProcessHealthScoreEngine()
        low.update([_fact(FactType.PROCESS_FAILURE, "Kat Hizmetleri", "Room Cleaning", SeverityLevel.LOW)])

        assert critical.compute()["Kat Hizmetleri"]["overall_health"] < low.compute()["Kat Hizmetleri"]["overall_health"]
