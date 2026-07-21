"""
Oturum bazlı sohbet geçmişi ve bağlam takibi.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Optional

from app.services.turkish_nlp_utils import normalize_turkish

_MAX_MESSAGES = 10

_FOOD_MARKERS = (
    "kahvalti", "kahvaltı", "yemek", "restoran", "menu", "menü", "bufe", "büfe",
    "vegan", "vejetaryen", "glutensiz", "icecek", "içecek", "bar", "breakfast",
)

_ROOM_PATTERN = __import__("re").compile(r"\b(?:oda\s+)?(\d{3,4})\b")


class ConversationStore:
    """In-memory session history and entity/topic context."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._context: dict[str, dict[str, Any]] = defaultdict(dict)
        self._lock = threading.Lock()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        if not session_id or not content:
            return
        with self._lock:
            msgs = self._sessions[session_id]
            msgs.append({
                "role": role,
                "content": content,
                "metadata": metadata or {},
            })
            if len(msgs) > _MAX_MESSAGES:
                self._sessions[session_id] = msgs[-_MAX_MESSAGES:]

    def get_history(self, session_id: str, limit: int = _MAX_MESSAGES) -> list[dict[str, Any]]:
        if not session_id:
            return []
        with self._lock:
            return list(self._sessions.get(session_id, [])[-limit:])

    def update_context(self, session_id: str, **kwargs: Any) -> None:
        if not session_id:
            return
        with self._lock:
            ctx = self._context[session_id]
            ctx.update({k: v for k, v in kwargs.items() if v is not None})

    def get_context(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            return {}
        with self._lock:
            return dict(self._context.get(session_id, {}))

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._context.pop(session_id, None)

    def has_food_context(self, session_id: str) -> bool:
        ctx = self.get_context(session_id)
        if ctx.get("topic") in ("food", "breakfast", "vegan"):
            return True
        combined = self._combined_user_text(session_id)
        norm = normalize_turkish(combined.lower())
        return any(m in norm for m in _FOOD_MARKERS)

    def has_vegan_context(self, session_id: str) -> bool:
        ctx = self.get_context(session_id)
        if ctx.get("topic") == "vegan":
            return True
        combined = self._combined_user_text(session_id)
        norm = normalize_turkish(combined.lower())
        return "vegan" in norm or "vejetaryen" in norm

    def get_last_room(self, session_id: str) -> Optional[str]:
        ctx = self.get_context(session_id)
        if ctx.get("last_room"):
            return str(ctx["last_room"])
        for msg in reversed(self.get_history(session_id)):
            if msg.get("role") != "user":
                continue
            m = _ROOM_PATTERN.search(normalize_turkish(msg.get("content", "").lower()))
            if m:
                return m.group(1)
        return None

    def _combined_user_text(self, session_id: str) -> str:
        return " ".join(
            m.get("content", "")
            for m in self.get_history(session_id)
            if m.get("role") == "user"
        )

    def record_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_answer: str,
        intent_data: dict[str, Any],
    ) -> None:
        if not session_id:
            return
        self.add_message(session_id, "user", user_query)
        self.add_message(
            session_id,
            "assistant",
            assistant_answer,
            metadata={"intent": intent_data.get("intent"), "mode": intent_data.get("mode")},
        )
        intent = intent_data.get("intent", "")
        entities = intent_data.get("entities") or {}
        updates: dict[str, Any] = {}

        if entities.get("room_number"):
            updates["last_room"] = entities["room_number"]
        elif intent in ("room_issue", "room_history", "bare_number"):
            room = entities.get("room_number")
            if room:
                updates["last_room"] = room

        if intent in (
            "breakfast_menu", "meal_menu_today", "daily_meal_menu",
            "vegan_options", "breakfast_hours", "contextual_neler_var",
        ):
            norm_q = normalize_turkish(user_query.lower())
            updates["topic"] = "vegan" if "vegan" in norm_q or "vejetaryen" in norm_q else "food"

        updates["last_intent"] = intent

        if updates:
            self.update_context(session_id, **updates)


_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
