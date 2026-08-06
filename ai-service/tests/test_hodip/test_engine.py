from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.engine import HodipEngine


@pytest.fixture
def engine() -> HodipEngine:
    return HodipEngine()


class TestEngine:
    def test_simple_review(self, engine: HodipEngine):
        result = engine.analyze("Odaya girdigimizde balkonda kus yuvasi vardi.", "r1")
        assert result["summary"]["fact_count"] >= 1

    def test_multi_clause(self, engine: HodipEngine):
        result = engine.analyze("Klima calismiyor. Havlu yok.", "r2")
        assert result["summary"]["clause_count"] >= 2
        assert result["summary"]["fact_count"] >= 2

    def test_empty_review(self, engine: HodipEngine):
        result = engine.analyze("", "r_empty")
        assert result["summary"]["clause_count"] == 0
        assert result["summary"]["fact_count"] == 0

    def test_report_structure(self, engine: HodipEngine):
        result = engine.analyze("Kahvalti soguktu. Klima calismiyor.", "r3")
        assert "process_health" in result
        assert "facts" in result
        assert "summary" in result
        assert len(result["clauses"]) >= 2
