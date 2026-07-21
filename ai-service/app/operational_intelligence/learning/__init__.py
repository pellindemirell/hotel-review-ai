"""
Learning pipeline — self-learning infrastructure for HODIP v3.0.

Every module has two modes:
  - rule: fast, deterministic, always available
  - learned: slow, probabilistic, improves over time

All modules follow the same interface:
    predict(clause, context) → (result, confidence, method)
"""

from .operational_embedder import OperationalEmbedder
from .memory_graph import OperationalMemoryGraph
from .confidence_learner import ConfidenceLearner
from .trend_analyzer import TrendAnalyzer

__all__ = [
    "OperationalEmbedder",
    "OperationalMemoryGraph",
    "ConfidenceLearner",
    "TrendAnalyzer",
]
