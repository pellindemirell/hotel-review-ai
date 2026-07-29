from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.learning.operational_embedder import OperationalEmbedder, EmbeddingResult


@pytest.fixture
def embedder() -> OperationalEmbedder:
    return OperationalEmbedder()


class TestColdStart:
    def test_bird_nest_match(self, embedder: OperationalEmbedder):
        result = embedder.find_nearest_failure("Odaya girdigimizde balkonda kus yuvasi vardi.")
        assert result is not None
        assert result.failure_key == "kus_yuvasi"
        assert result.confidence >= 0.0
        assert result.method == "exact_match"

    def test_hvac_match(self, embedder: OperationalEmbedder):
        result = embedder.find_nearest_failure("Klima calismiyor, oda cok sicak.")
        assert result is not None
        assert result.failure_key == "klima_ariza"
        assert result.method == "exact_match"

    def test_towel_match(self, embedder: OperationalEmbedder):
        result = embedder.find_nearest_failure("Havlu istedik getirmediler.")
        assert result is not None
        assert result.failure_key == "havlu_talebi"
        assert result.method == "exact_match"

    def test_empty_clause(self, embedder: OperationalEmbedder):
        result = embedder.find_nearest_failure("")
        assert result is None or result.confidence == 0.0

    def test_unknown_clause_uses_jaccard(self, embedder: OperationalEmbedder):
        result = embedder.find_nearest_failure("Balkon tertemizdi, hic sorun yok.")
        # May return None if no prototype exceeds threshold
        if result is not None:
            assert result.confidence >= 0.0
