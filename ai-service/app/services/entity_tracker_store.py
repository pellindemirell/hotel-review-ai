"""
Genelleştirilmiş entity sorun takibi — oda, tesis, uygulama, kargo vb.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "entity_tracker_store.json",
)

_lock = threading.Lock()


@dataclass
class EntityIssue:
    id: str
    entity_id: str
    entity_type: str
    entity_label: str
    issue_type: str
    status: str  # open | resolved | scheduled
    domain: str = ""
    department: str = ""
    first_reported: str = ""
    last_reported: str = ""
    resolved_at: Optional[str] = None
    scheduled_date: Optional[str] = None
    comment_ids: list[str] = field(default_factory=list)
    notes: str = ""
    room_number: Optional[str] = None  # backward compat

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityComment:
    id: str
    entity_id: str
    entity_type: str
    entity_label: str
    comment: str
    issue_type: Optional[str]
    review_id: Optional[str]
    created_at: str
    is_resolution: bool = False
    domain: str = ""
    department: str = ""
    room_number: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntityTrackerStore:
    """Thread-safe entity sorun deposu."""

    def __init__(self, path: str = _STORE_PATH) -> None:
        self.path = path
        self._issues: list[EntityIssue] = []
        self._comments: list[EntityComment] = []
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.isfile(self.path):
            self._issues = []
            self._comments = []
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self._issues = [EntityIssue(**i) for i in raw.get("issues", [])]
            self._comments = [EntityComment(**c) for c in raw.get("comments", [])]
        except (OSError, json.JSONDecodeError, TypeError):
            self._issues = []
            self._comments = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, encoding="utf-8", mode="w") as f:
            json.dump(
                {
                    "version": 1,
                    "issue_count": len(self._issues),
                    "comment_count": len(self._comments),
                    "issues": [i.to_dict() for i in self._issues],
                    "comments": [c.to_dict() for c in self._comments],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def all_issues(self) -> list[EntityIssue]:
        with _lock:
            return list(self._issues)

    def all_comments(self) -> list[EntityComment]:
        with _lock:
            return list(self._comments)

    def add_issue(self, issue: EntityIssue) -> EntityIssue:
        with _lock:
            self._issues.append(issue)
            self._save()
        return issue

    def update_issue(self, issue: EntityIssue) -> EntityIssue:
        with _lock:
            for idx, existing in enumerate(self._issues):
                if existing.id == issue.id:
                    self._issues[idx] = issue
                    self._save()
                    return issue
            self._issues.append(issue)
            self._save()
        return issue

    def add_comment(self, comment: EntityComment) -> EntityComment:
        with _lock:
            self._comments.append(comment)
            self._save()
        return comment

    def find_open_issue(self, entity_id: str, issue_type: str) -> Optional[EntityIssue]:
        with _lock:
            for issue in self._issues:
                if (
                    issue.entity_id == entity_id
                    and issue.issue_type == issue_type
                    and issue.status in ("open", "scheduled")
                ):
                    return issue
        return None

    def clear(self) -> None:
        with _lock:
            self._issues = []
            self._comments = []
            self._save()

    def count(self) -> int:
        with _lock:
            return len(self._issues)


_store: Optional[EntityTrackerStore] = None


def get_entity_tracker_store() -> EntityTrackerStore:
    global _store
    if _store is None:
        _store = EntityTrackerStore()
    return _store
