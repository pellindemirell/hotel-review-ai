"""
Confidence Learning — calibrated confidence from model probability.

Current state: hardcoded confidence (0.95 for rules, 0.75 for inference, etc.)
Target state: calibrated probability from model + isotonic regression

Every prediction stores:
  - raw_score (model output / similarity)
  - calibrated_confidence (post-calibration)
  - calibration_method
  - is_verified (human confirmed?)
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CalibrationRecord:
    raw_score: float
    calibrated: float
    was_correct: Optional[bool] = None
    method: str = "rule"  # rule | jaccard | embedding | ensemble

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_score": self.raw_score,
            "calibrated": self.calibrated,
            "was_correct": self.was_correct,
            "method": self.method,
        }


class ConfidenceLearner:
    """
    Learns to calibrate raw model scores into meaningful confidence values.

    Cold start: no calibration, raw_score = confidence
    After 100+ verified predictions: isotonic regression per method
    """

    def __init__(self, persist_path: str = "") -> None:
        self._records: list[CalibrationRecord] = []
        self._calibrators: dict[str, Any] = {}
        self._persist_path = persist_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "confidence_calibrator.pkl"
        )
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._persist_path):
            try:
                with open(self._persist_path, "rb") as f:
                    data = pickle.load(f)
                self._records = data.get("records", [])
                self._calibrators = data.get("calibrators", {})
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, "wb") as f:
            pickle.dump({
                "records": self._records,
                "calibrators": self._calibrators,
            }, f)

    def calibrate(self, raw_score: float, method: str = "rule") -> float:
        """Convert raw score to calibrated confidence."""
        if method in self._calibrators and len(self._records) >= 100:
            try:
                cal = self._calibrators[method]
                return float(cal.predict([[raw_score]])[0])
            except Exception:
                pass

        # Cold start: simple scaling
        if method == "exact_match":
            return min(0.98, raw_score * 0.98)
        elif method == "jaccard":
            return min(0.75, raw_score * 0.85)
        elif method == "embedding":
            return min(0.85, raw_score * 0.9)
        elif method == "ensemble":
            return min(0.92, raw_score * 0.95)
        return min(0.90, raw_score)

    def record_feedback(
        self, raw_score: float, calibrated: float, was_correct: bool, method: str
    ) -> None:
        """Store a prediction outcome for future calibration."""
        record = CalibrationRecord(
            raw_score=raw_score,
            calibrated=calibrated,
            was_correct=was_correct,
            method=method,
        )
        self._records.append(record)

        # Retrain calibrator every 50 new records
        if len(self._records) % 50 == 0 and len(self._records) >= 100:
            self._train_calibrators()

    def _train_calibrators(self) -> None:
        """Train isotonic regression per method."""
        try:
            from sklearn.isotonic import IsotonicRegression

            for method in set(r.method for r in self._records):
                method_records = [r for r in self._records if r.method == method and r.was_correct is not None]
                if len(method_records) < 20:
                    continue

                X = [[r.raw_score] for r in method_records]
                y = [1.0 if r.was_correct else 0.0 for r in method_records]

                iso_reg = IsotonicRegression(out_of_bounds="clip")
                iso_reg.fit([x[0] for x in X], y)
                self._calibrators[method] = iso_reg

            self.save()
        except ImportError:
            pass  # sklearn not available, keep cold start

    def summary(self) -> dict[str, Any]:
        total = len(self._records)
        verified = sum(1 for r in self._records if r.was_correct is not None)
        correct = sum(1 for r in self._records if r.was_correct)
        return {
            "total_records": total,
            "verified_records": verified,
            "accuracy": round(correct / verified, 3) if verified else None,
            "calibrators_trained": list(self._calibrators.keys()),
            "methods_available": list(set(r.method for r in self._records)),
        }
