"""Aspect extraction — adapter over HotelOntologyEngine (DOC-002)."""

from __future__ import annotations

from app.ontology.engine import HotelOntologyEngine, get_hotel_ontology_engine
from app.ontology.models import AspectMapping, EntityRef


class AspectExtractor:
    """Stage 6–7: Entity + Aspect extraction via ontology engine."""

    def __init__(self, engine: HotelOntologyEngine | None = None) -> None:
        self._engine = engine or get_hotel_ontology_engine()

    @property
    def engine(self) -> HotelOntologyEngine:
        return self._engine

    def extract_entities(self, clause: str, lang: str = "tr") -> list[EntityRef]:
        refs: list[EntityRef] = []
        primary = self._engine.resolve_term(clause, lang=lang)
        if primary.confidence >= 0.55 and primary.entity_id:
            refs.append(primary)
        return refs

    def extract_aspect(self, clause: str, lang: str = "tr") -> AspectMapping:
        return self._engine.map_aspect(clause, lang=lang)
