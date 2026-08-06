"""Hotel ontology engine — config-driven entity, aspect, synonym resolution."""

from app.ontology.engine import HotelOntologyEngine
from app.ontology.models import AspectMapping, EntityRef, Segment

__all__ = ["HotelOntologyEngine", "EntityRef", "AspectMapping", "Segment"]
