"""Data models for hotel ontology engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EntityRef:
    entity_id: str
    entity_type: str
    label: str
    confidence: float
    lang: str = "tr"
    matched_term: str = ""
    department: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "label": self.label,
            "confidence": self.confidence,
            "lang": self.lang,
            "matched_term": self.matched_term,
            "department": self.department,
        }


@dataclass
class AspectMapping:
    aspect: str
    aspect_label: str
    department: str
    department_label: str
    category: str
    confidence: float
    method: str = "config"
    matched_term: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect": self.aspect,
            "aspect_label": self.aspect_label,
            "department": self.department,
            "department_label": self.department_label,
            "category": self.category,
            "confidence": self.confidence,
            "method": self.method,
            "matched_term": self.matched_term,
        }


@dataclass
class Segment:
    index: int
    text: str
    aspect: Optional[str] = None
    aspect_category: Optional[str] = None
    department: Optional[str] = None
    department_label: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: float = 0.0
    entity_refs: list[EntityRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "aspect": self.aspect,
            "aspect_category": self.aspect_category,
            "department": self.department,
            "department_label": self.department_label,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "entity_refs": [r.to_dict() for r in self.entity_refs],
        }
