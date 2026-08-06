from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.operational_intelligence.learning.confidence_learner import ConfidenceLearner


class TestCalibration:
    def test_calibrate_cold_start(self):
        learner = ConfidenceLearner()
        calibrated = learner.calibrate(0.85)
        assert calibrated == 0.85

    def test_calibrate_with_feedback(self):
        learner = ConfidenceLearner()
        learner.record_feedback(0.85, 0.82, True, "rule")
        learner.record_feedback(0.80, 0.78, True, "rule")
        learner.record_feedback(0.90, 0.88, True, "rule")
        calibrated = learner.calibrate(0.85, "rule")
        assert 0.0 <= calibrated <= 1.0

    def test_jaccard_scaling(self):
        learner = ConfidenceLearner()
        calibrated = learner.calibrate(0.85, "jaccard")
        assert calibrated <= 0.75

    def test_embedding_scaling(self):
        learner = ConfidenceLearner()
        calibrated = learner.calibrate(0.85, "embedding")
        assert calibrated <= 0.85
