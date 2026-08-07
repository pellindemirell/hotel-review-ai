from __future__ import annotations

import os
import sys
import tempfile

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.learning.memory_graph import OperationalMemoryGraph


@pytest.fixture
def tmp_mg(tmp_path):
    p = str(tmp_path / "memory_graph.pkl")
    return OperationalMemoryGraph(persist_path=p)


class TestCaseMemory:
    def test_memorize_creates_case(self, tmp_mg):
        mg = tmp_mg
        cid = mg.memorize("Klima calismiyor.", "hvac_failure", "AC Failure", "r1")
        assert cid is not None
        cases = mg.get_cases_for_review("r1")
        assert len(cases) > 0
        assert cases[0].failure_key == "hvac_failure"

    def test_same_pattern_merged(self, tmp_mg):
        mg = tmp_mg
        cid1 = mg.memorize("Klima calismiyor", "hvac_failure", "AC Failure", "r1")
        cid2 = mg.memorize("Oda buz gibi", "hvac_failure", "AC Failure", "r2")
        assert cid1 == cid2

    def test_get_trending_empty(self, tmp_mg):
        mg = tmp_mg
        assert mg.get_trending() == []

    def test_get_trending_with_data(self, tmp_mg):
        mg = tmp_mg
        for i in range(5):
            mg.memorize("test", "bird_nest", "Bird Nest", f"r{i}")
        assert len(mg.get_all_cases()) > 0

    def test_persist_and_load(self, tmp_path):
        p = str(tmp_path / "memory_graph.pkl")
        mg = OperationalMemoryGraph(persist_path=p)
        mg.memorize("Klima calismiyor", "hvac_failure", "AC Failure", "r1")
        mg.save()

        mg2 = OperationalMemoryGraph(persist_path=p)
        cases = mg2.get_cases_for_review("r1")
        assert len(cases) > 0

    def test_new_patterns(self, tmp_mg):
        mg = tmp_mg
        mg.memorize("t1", "new_issue", "New Issue", "r1")
        mg.memorize("t2", "new_issue", "New Issue", "r2")
        patterns = mg.get_new_patterns(min_occurrences=2)
        assert len(patterns) > 0
