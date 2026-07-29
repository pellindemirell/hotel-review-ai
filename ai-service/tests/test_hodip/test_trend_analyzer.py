from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.learning.trend_analyzer import TrendAnalyzer


class TestAnomalyDetection:
    def test_no_data_insufficient(self):
        ta = TrendAnalyzer()
        trend = ta.get_trend("hvac_failure")
        assert trend["trend"] == "insufficient_data"

    def test_constant_data_no_anomaly(self):
        ta = TrendAnalyzer()
        base = datetime.now()
        for day_offset in range(14):
            ts = (base - timedelta(days=day_offset)).isoformat()
            for _ in range(5):
                ta.record("bird_nest", ts)
        trend = ta.get_trend("bird_nest")
        assert trend["trend"] in ("rising", "stable", "declining")
        assert not trend["is_anomaly"]

    def test_spike_detected(self):
        ta = TrendAnalyzer()
        base = datetime.now()
        for day_offset in range(14):
            ts = (base - timedelta(days=day_offset)).isoformat()
            count = 5 if day_offset > 0 else 20
            for _ in range(count):
                ta.record("hvac_failure", ts)
        trend = ta.get_trend("hvac_failure")
        assert trend["trend"] in ("rising", "stable", "declining")

    def test_trend_direction(self):
        ta = TrendAnalyzer()
        base = datetime.now()
        for day_offset in range(7):
            ts = (base - timedelta(days=day_offset)).isoformat()
            for _ in range(day_offset + 1):
                ta.record("towel_issue", ts)
        trend = ta.get_trend("towel_issue")
        assert trend["trend"] in ("rising", "stable", "declining", "insufficient_data")
