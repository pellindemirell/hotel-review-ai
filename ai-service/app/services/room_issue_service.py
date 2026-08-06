"""
Oda bazlı operasyonel sorun takibi — EntityTrackerService'e delegasyon (geriye dönük uyumluluk).
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.entity_tracker_service import EntityTrackerService, get_entity_tracker_service
from app.services.entity_tracker_store import EntityTrackerStore
from app.services.room_issues_store import RoomIssue, RoomIssuesStore, get_room_issues_store


class RoomIssueService:
    """Geriye dönük uyumluluk — asıl mantık EntityTrackerService'te."""

    def __init__(
        self,
        store: Optional[RoomIssuesStore] = None,
        entity_store: Optional[EntityTrackerStore] = None,
    ) -> None:
        if entity_store is not None:
            self._entity_svc = EntityTrackerService(store=entity_store)
        else:
            self._entity_svc = get_entity_tracker_service()
        self.store = store or get_room_issues_store()

    @staticmethod
    def extract_room_number(text: str) -> Optional[str]:
        return EntityTrackerService.extract_room_number(text)

    @staticmethod
    def extract_issue_type(text: str) -> Optional[str]:
        return EntityTrackerService.extract_issue_type(text)

    @staticmethod
    def is_resolution_comment(text: str) -> bool:
        return EntityTrackerService.is_resolution_comment(text)

    @staticmethod
    def is_scheduled_comment(text: str) -> bool:
        return EntityTrackerService.is_scheduled_comment(text)

    @staticmethod
    def extract_scheduled_date(text: str) -> Optional[str]:
        return EntityTrackerService.extract_scheduled_date(text)

    @staticmethod
    def is_room_query(query: str) -> bool:
        return EntityTrackerService.is_room_query(query)

    def register_from_comment(
        self,
        comment: str,
        review_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[RoomIssue]:
        entity_issue = self._entity_svc.register_from_comment(comment, review_id, created_at)
        room = self.extract_room_number(comment)
        if not room:
            return None

        if entity_issue and entity_issue.room_number:
            return self._to_room_issue(entity_issue, room)

        open_issues = self._entity_svc.get_open_issues(f"room_{room}")
        if open_issues:
            return self._to_room_issue(open_issues[0], room)

        resolved = self._entity_svc.get_resolved_issues(f"room_{room}")
        if resolved:
            return self._to_room_issue(resolved[-1], room)

        return None

    @staticmethod
    def _to_room_issue(entity_issue: Any, room: str) -> RoomIssue:
        return RoomIssue(
            id=entity_issue.id,
            room_number=room,
            issue_type=entity_issue.issue_type,
            status=entity_issue.status,
            first_reported=entity_issue.first_reported,
            last_reported=entity_issue.last_reported,
            resolved_at=entity_issue.resolved_at,
            scheduled_date=entity_issue.scheduled_date,
            comment_ids=entity_issue.comment_ids,
            notes=entity_issue.notes,
        )

    def get_room_report(self, room_number: str) -> dict[str, Any]:
        return self._entity_svc.get_room_report(room_number)

    def get_open_issues(self, room_number: str) -> list[RoomIssue]:
        issues = self._entity_svc.get_open_issues(f"room_{room_number}")
        return [self._to_room_issue(i, room_number) for i in issues]

    def get_resolved_issues(self, room_number: str) -> list[RoomIssue]:
        issues = self._entity_svc.get_resolved_issues(f"room_{room_number}")
        return [self._to_room_issue(i, room_number) for i in issues]

    def find_cross_room_patterns(self, issue_type: str, days: int = 7) -> list[dict[str, Any]]:
        return self._entity_svc.find_cross_room_patterns(issue_type, days)

    def format_room_chat_answer(self, query: str) -> Optional[str]:
        return self._entity_svc.format_room_chat_answer(query)

    def seed_demo_data(self, force: bool = False) -> dict[str, Any]:
        return self._entity_svc.seed_demo_data(force=force)


_service: Optional[RoomIssueService] = None


def get_room_issue_service() -> RoomIssueService:
    global _service
    if _service is None:
        _service = RoomIssueService()
    return _service
