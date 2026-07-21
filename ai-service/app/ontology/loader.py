"""YAML/JSON config loader for hotel ontology."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_AI_SERVICE_ONTOLOGY = Path(__file__).resolve().parents[2] / "config" / "ontology"
_REPO_HOTEL_AI_ONTOLOGY = (
    Path(__file__).resolve().parents[3] / "hotel-ai" / "datasets" / "ontology" / "v1"
)


def _resolve_config_dir(config_dir: str | Path | None) -> Path:
    if config_dir:
        return Path(config_dir)
    env_dir = os.environ.get("ONTOLOGY_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    if _REPO_HOTEL_AI_ONTOLOGY.is_dir() and (_REPO_HOTEL_AI_ONTOLOGY / "aspects.yaml").exists():
        return _REPO_HOTEL_AI_ONTOLOGY
    return _AI_SERVICE_ONTOLOGY


_DEFAULT_CONFIG_DIR = _AI_SERVICE_ONTOLOGY


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "PyYAML required for ontology config. Install: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return data if isinstance(data, dict) else {}


class OntologyConfigLoader:
    """Loads and caches ontology config files."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        self.config_dir = _resolve_config_dir(config_dir)
        self._cache: dict[str, Any] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _load_split_entities(self) -> dict[str, Any]:
        """Merge hotel-ai v1 split files (equipment.yaml + services.yaml)."""
        equipment_path = self.config_dir / "equipment.yaml"
        if not equipment_path.exists():
            return {}
        equipment_data = _load_yaml_or_json(equipment_path)
        merged: dict[str, Any] = {
            "physical": equipment_data.get("physical", []),
            "facilities": equipment_data.get("facilities", []),
            "human": equipment_data.get("human", []),
            "equipment": equipment_data.get("equipment", []),
        }
        services_path = self.config_dir / "services.yaml"
        if services_path.exists():
            services_data = _load_yaml_or_json(services_path)
            for svc in services_data.get("services", []):
                merged.setdefault("equipment", []).append({
                    **svc,
                    "subtype": svc.get("subtype", "service"),
                })
        return merged

    def load_entities(self) -> dict[str, Any]:
        if "entities" not in self._cache:
            entities_path = self.config_dir / "entities.yaml"
            if entities_path.exists():
                self._cache["entities"] = _load_yaml_or_json(entities_path)
            else:
                split = self._load_split_entities()
                self._cache["entities"] = split if split else _load_yaml_or_json(
                    _AI_SERVICE_ONTOLOGY / "entities.yaml"
                )
        return self._cache["entities"]

    def load_departments(self) -> dict[str, Any]:
        key = "departments"
        if key not in self._cache:
            path = self.config_dir / "departments.yaml"
            if path.exists():
                self._cache[key] = _load_yaml_or_json(path)
            else:
                self._cache[key] = {"departments": []}
        return self._cache[key]

    def load_relationships(self) -> dict[str, Any]:
        if "relationships" not in self._cache:
            self._cache["relationships"] = _load_yaml_or_json(self.config_dir / "relationships.yaml")
        return self._cache["relationships"]

    def load_responsibilities(self) -> dict[str, Any]:
        if "responsibilities" not in self._cache:
            self._cache["responsibilities"] = _load_yaml_or_json(
                self.config_dir / "responsibilities.yaml"
            )
        return self._cache["responsibilities"]

    def load_aspects(self) -> dict[str, Any]:
        if "aspects" not in self._cache:
            self._cache["aspects"] = _load_yaml_or_json(self.config_dir / "aspects.yaml")
        return self._cache["aspects"]

    def load_synonyms(self, lang: str) -> dict[str, Any]:
        key = f"synonyms_{lang}"
        if key not in self._cache:
            path = self.config_dir / "synonyms" / f"{lang}.yaml"
            if not path.exists():
                self._cache[key] = {"synonyms": []}
            else:
                self._cache[key] = _load_yaml_or_json(path)
        return self._cache[key]

    def load_all_synonyms(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        syn_dir = self.config_dir / "synonyms"
        if syn_dir.is_dir():
            for f in syn_dir.glob("*.yaml"):
                lang = f.stem
                result[lang] = self.load_synonyms(lang).get("synonyms", [])
        return result
