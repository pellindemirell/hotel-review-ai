from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.knowledge_graph import KnowledgeGraphBuilder
from app.operational_intelligence.models import FactType
from tests.test_hodip.fixtures import TEST_CLAUSES


@pytest.fixture
def kg() -> KnowledgeGraphBuilder:
    return KnowledgeGraphBuilder()


class TestPatterns:
    def test_bird_nest(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Odaya girdigimizde balkonda kus yuvasi vardi.", "r1", 0)
        assert len(facts) >= 2
        ftypes = {f.fact_type for f in facts}
        assert FactType.OBSERVATION in ftypes

    def test_bird_nest_department(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Odaya girdigimizde balkonda kus yuvasi vardi.", "r1", 0)
        pfs = [f for f in facts if f.fact_type == FactType.PROCESS_FAILURE]
        assert len(pfs) > 0
        assert pfs[0].department != ""

    def test_hvac_failure(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Klima calismiyor, oda buz gibi.", "r1", 0)
        assert len(facts) >= 2

    def test_towel_request(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Havlu istedik 3 kere aradik getirmediler.", "r1", 0)
        assert len(facts) >= 2

    def test_cold_food(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Kahvalti soguktu.", "r1", 0)
        assert len(facts) >= 2


class TestEdgeCases:
    def test_empty_clause(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("", "r1", 0)
        assert len(facts) == 0

    def test_no_match_returns_empty(self, kg: KnowledgeGraphBuilder):
        facts = kg._analyze_clause("Cok guzeldi.", "r1", 0)
        assert len(facts) == 0


class TestBuild:
    def test_build_returns_list(self, kg: KnowledgeGraphBuilder):
        clauses = ["Klima calismiyor.", "Havlu yoktu."]
        facts = kg.build(clauses, "r1")
        assert isinstance(facts, list)
        assert len(facts) >= 2

    def test_build_all_fixtures(self, kg: KnowledgeGraphBuilder):
        clauses = [c for c, f, d, n in TEST_CLAUSES if len(c.strip()) > 5]
        facts = kg.build(clauses, "r_all")
        assert len(facts) >= 5
