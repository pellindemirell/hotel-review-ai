"""
Oda bazlı sorun kayıtları — JSON kalıcılık + demo seed.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "room_issues_store.json",
)

_lock = threading.Lock()


@dataclass
class RoomIssue:
    id: str
    room_number: str
    issue_type: str
    status: str  # open | resolved | scheduled
    first_reported: str
    last_reported: str
    resolved_at: Optional[str] = None
    scheduled_date: Optional[str] = None
    comment_ids: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoomComment:
    """Oda etiketli yorum kaydı (review_store ile bağlantılı)."""
    id: str
    room_number: str
    comment: str
    issue_type: Optional[str]
    review_id: Optional[str]
    created_at: str
    is_resolution: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RoomIssuesStore:
    """Thread-safe oda sorun deposu."""

    def __init__(self, path: str = _STORE_PATH) -> None:
        self.path = path
        self._issues: list[RoomIssue] = []
        self._comments: list[RoomComment] = []
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
            self._issues = [RoomIssue(**i) for i in raw.get("issues", [])]
            self._comments = [RoomComment(**c) for c in raw.get("comments", [])]
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

    def all_issues(self) -> list[RoomIssue]:
        with _lock:
            return list(self._issues)

    def all_comments(self) -> list[RoomComment]:
        with _lock:
            return list(self._comments)

    def add_issue(self, issue: RoomIssue) -> RoomIssue:
        with _lock:
            self._issues.append(issue)
            self._save()
        return issue

    def update_issue(self, issue: RoomIssue) -> RoomIssue:
        with _lock:
            for idx, existing in enumerate(self._issues):
                if existing.id == issue.id:
                    self._issues[idx] = issue
                    self._save()
                    return issue
            self._issues.append(issue)
            self._save()
        return issue

    def add_comment(self, comment: RoomComment) -> RoomComment:
        with _lock:
            self._comments.append(comment)
            self._save()
        return comment

    def find_open_issue(self, room_number: str, issue_type: str) -> Optional[RoomIssue]:
        with _lock:
            for issue in self._issues:
                if (
                    issue.room_number == room_number
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


_store: Optional[RoomIssuesStore] = None


def get_room_issues_store() -> RoomIssuesStore:
    global _store
    if _store is None:
        _store = RoomIssuesStore()
    return _store
