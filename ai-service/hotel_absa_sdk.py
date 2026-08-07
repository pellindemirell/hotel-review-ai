"""
Hotel ABSA (Aspect-Based Sentiment Analysis) Standalone Python SDK
Allows direct in-memory Python calls without needing an HTTP REST server.

Usage:
    from hotel_absa_sdk import HotelAbsaEngine

    engine = HotelAbsaEngine()
    result = engine.analyze("Kahvaltı harikaydı ama oda biraz küçüktü.")
    print(result)
"""

import sys
import os

# Auto-add parent directory to path for transparent imports
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from app.services.clause_pipeline import classify_clause
from app.services.absa_service import AbsaService

class HotelAbsaEngine:
    def __init__(self):
        """Initializes the ABSA Rule & Ontology Engine."""
        pass

    def analyze_clause(self, clause_text: str) -> dict:
        """Classifies a single clause into Department, Aspect, and Sentiment."""
        res = classify_clause(clause_text)
        return {
            "clause": clause_text,
            "department": res.department_label or "Genel",
            "aspect": res.aspect_label or "Genel",
            "sentiment": res.sentiment or "Neutral",
            "sentimentScore": getattr(res, "score", 0.0),
            "confidence": getattr(res, "confidence", 0.95),
            "keywords": res.keywords or []
        }

    def analyze(self, comment_text: str, rating: int = None) -> dict:
        """Splits full comment into clauses and performs multi-aspect department ABSA analysis."""
        absa_res = AbsaService.analyze(comment_text, rating=rating)
        return AbsaService.to_dict(absa_res)

# Global singleton helper
_default_engine = HotelAbsaEngine()

def analyze_review(comment: str, rating: int = None) -> dict:
    """Convenience function for instant 1-line analysis."""
    return _default_engine.analyze(comment, rating=rating)

def classify_text(clause: str) -> dict:
    """Convenience function for single clause classification."""
    return _default_engine.analyze_clause(clause)
