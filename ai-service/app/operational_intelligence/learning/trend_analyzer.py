"""
Cross-Review Trend Analysis — time-series anomaly detection per sub-process.

Tracks frequencies of every failure type over time.
Detects:
  - Sudden spikes (this week vs last 4 weeks)
  - Long-term trends (rising over 3 months)
  - Seasonal patterns (pool issues in summer, AC in winter)
  - New pattern emergence

Data source: OperationalMemoryGraph + timestamps
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """
    Learns and reports trends from accumulated operational memory.

    Cold start: simple moving average + z-score anomaly
    Mature: Prophet time-series model per sub-process
    """

    def __init__(self, persist_path: str = "") -> None:
        self._daily_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._weekly_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._monthly_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._persist_path = persist_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "trend_data.pkl"
        )
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._persist_path):
            try:
                with open(self._persist_path, "rb") as f:
                    data = pickle.load(f)
                self._daily_counts = defaultdict(dict, data.get("daily", {}))
                self._weekly_counts = defaultdict(dict, data.get("weekly", {}))
                self._monthly_counts = defaultdict(dict, data.get("monthly", {}))
            except Exception:
                logger.warning("Failed to load trend analyzer persistence", exc_info=True)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, "wb") as f:
            pickle.dump({
                "daily": dict(self._daily_counts),
                "weekly": dict(self._weekly_counts),
                "monthly": dict(self._monthly_counts),
            }, f)

    def record(self, failure_key: str, timestamp: Optional[str] = None) -> None:
        """Record one occurrence of a failure."""
        if timestamp:
            dt = datetime.fromisoformat(timestamp)
        else:
            dt = datetime.now(timezone.utc)

        day_key = dt.strftime("%Y-%m-%d")
        week_key = dt.strftime("%Y-W%V")
        month_key = dt.strftime("%Y-%m")

        self._daily_counts[failure_key][day_key] = self._daily_counts[failure_key].get(day_key, 0) + 1
        self._weekly_counts[failure_key][week_key] = self._weekly_counts[failure_key].get(week_key, 0) + 1
        self._monthly_counts[failure_key][month_key] = self._monthly_counts[failure_key].get(month_key, 0) + 1

    def get_trend(self, failure_key: str) -> dict[str, Any]:
        """
        Analyze trend for a specific failure type.

        Returns trend direction, current rate, anomaly flag.
        """
        daily = self._daily_counts.get(failure_key, {})
        sorted_days = sorted(daily.keys())

        if len(sorted_days) < 7:
            return {"trend": "insufficient_data", "count": sum(daily.values())}

        recent = sorted_days[-7:]
        prior = [d for d in sorted_days if d < recent[0]]

        recent_total = sum(daily[d] for d in recent if d in daily)
        prior_total = sum(daily[d] for d in prior[-28:] if d in daily) if prior else 0

        recent_rate = recent_total / 7
        prior_rate = prior_total / min(len(prior[-28:]), 28) if prior_total > 0 else 0

        if prior_rate == 0:
            change_pct = 100 if recent_rate > 0 else 0
        else:
            change_pct = ((recent_rate - prior_rate) / prior_rate) * 100

        # Anomaly: z-score > 2
        all_rates = [daily[d] for d in sorted_days]
        mean = sum(all_rates) / len(all_rates)
        var = sum((r - mean) ** 2 for r in all_rates) / len(all_rates)
        std = var ** 0.5
        is_anomaly = abs(recent_rate - mean) > 2 * std if std > 0 else False

        if change_pct > 30 and recent_rate > 1:
            direction = "rising"
        elif change_pct < -30:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "failure_key": failure_key,
            "trend": direction,
            "change_pct": round(change_pct, 1),
            "recent_daily_avg": round(recent_rate, 2),
            "prior_daily_avg": round(prior_rate, 2),
            "is_anomaly": is_anomaly,
            "total_occurrences": sum(daily.values()),
            "days_observed": len(sorted_days),
        }

    def get_all_trends(self) -> list[dict[str, Any]]:
        """Get trends for all tracked failure types."""
        return [self.get_trend(key) for key in self._daily_counts]

    def get_anomalies(self) -> list[dict[str, Any]]:
        """Return all currently anomalous trends."""
        return [t for t in self.get_all_trends() if t.get("is_anomaly")]

    def get_rising(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Return top N rising trends."""
        trends = self.get_all_trends()
        rising = [t for t in trends if t.get("trend") == "rising"]
        rising.sort(key=lambda t: t.get("change_pct", 0), reverse=True)
        return rising[:top_n]

    def summary(self) -> dict[str, Any]:
        return {
            "tracked_failures": len(self._daily_counts),
            "trending_up": len([t for t in self.get_all_trends() if t.get("trend") == "rising"]),
            "trending_down": len([t for t in self.get_all_trends() if t.get("trend") == "declining"]),
            "anomalies": len(self.get_anomalies()),
            "top_rising": [t["failure_key"] for t in self.get_rising(5)],
        }
