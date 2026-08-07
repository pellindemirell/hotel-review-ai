"""OpsCopilotAdapter — routes staff ops queries through Gateway → Planner → Tools."""


from __future__ import annotations

import logging

import os
import re
import sys
from typing import Any, Optional

# Wire hotel-ops-copilot into PYTHONPATH
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_COPILOT_SRC = os.path.join(_ROOT, "hotel-ops-copilot")
if _COPILOT_SRC not in sys.path:
    sys.path.insert(0, _COPILOT_SRC)

try:
    from src.gateway.gateway import Gateway  # noqa: E402
except ImportError:
    class DummyMemory:
        def get_history(self, session_id):
            return []
        def add_turn(self, session_id, role, content, metadata):
            pass

    class Gateway:
        def __init__(self):
            self.memory = DummyMemory()
        def process(self, query, role=None, hotel_id=None, session_id=None):
            return {
                "answer": "Personel Copilot sistemi şu anda çevrimdışı (gateway modülü bulunamadı).",
                "plan": {},
                "tools_used": [],
                "resolved_query": {},
                "request_id": None,
                "tool_results": [],
            }


def _norm(text: str) -> str:
    return (
        text.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .strip()
    )


_OPS_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"gerekli\s+birim",
        r"birim.*ulass",
        r"birimlere\s+haber",
        r"notify|bildirim\s+gonder",
        r"ticket|kayit\s+ac|kaydı\s+aç",
        r"teknik\s+ekip|engineering.*gonder",
        r"sikayet.*(?:bu\s+hafta|gecen\s+hafta|trend)",
        r"(?:bu|gecen)\s+hafta.*sikayet",
        r"klima.*sikayet|sikayet.*klima",
        r"rapor|report|kpi|trend",
        r"cozuldu\s+mu|durum.*sorun|sorun.*cozul",
        r"gecen\s+hafta.*su|su\s+sorun",
        r"oncelik\s+kuyr|priority\s+queue",
        r"is\s+emri|work\s+order|atama|assign",
        r"kirli\s+oda|dirty\s+room|ooo\s+yap",
        r"temizlik\s+iste|cleaning\s+request",
        r"escalat|eskalasyon",
        r"oda\s+\d{2,4}.*(?:gonder|ticket|bildir)",
        r"daha\s+once.*sorun|daha\s+önce.*sorun",
        r"gecmis.*sorun|geçmiş.*sorun",
        r"oda\s+\d{2,4}.*(?:durum|kontrol|sorun)",
        r"^(evet|tamam|olur|klima|su|wifi|bilgi|rapor|ticket)$",
        r"ne\s+durumday",
        r"durum\s+ozeti|genel\s+durum",
        r"doluluk",
        r"odalarda.*proble",
        r"problemi\s+var",
        r"klima\s+sorunu\s+olan",
        r"acik\s+sikayet|açık\s+şikayet",
        r"acik\s+ticket|açık\s+ticket",
    )
]

_FAQ_EXCLUDE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"kahvalt",
        r"vegan",
        r"havuz\s+(?:saat|kaç|kapan|acil|açil|bit)",
        r"hangi\s+hizmet",
        r"bug[uü]n\s+yemekte",
        r"check.?in\s+saat",
        r"check.?out\s+saat",
        r"spa\s+hizmet",
        r"otopark",
        r"wifi\s+sifre|wifi\s+şifre",
        r"^neler\s+var$",
        r"^ne\s+var$",
    )
]

_SIMPLE_FAQ_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"^(merhaba|selam|iyi\s+günler|günaydın|hello|hi)\b",
        r"^(tesekkur|teşekkür|saol|sağol)",
        r"^(yardim|yardım|help)\b",
        r"^(neler\s+yapabil|yetenek|capabilities)",
    )
]


class OpsCopilotAdapter:
    """Detect ops/planner-worthy queries and route through hotel-ops-copilot Gateway."""

    def __init__(self) -> None:
        self._gateway = Gateway()

    @staticmethod
    def is_simple_faq_or_greeting(query: str) -> bool:
        q = (query or "").strip()
        if not q:
            return True
        return any(p.search(q) for p in _SIMPLE_FAQ_PATTERNS)

    @staticmethod
    def is_faq_query(query: str) -> bool:
        """Hotel knowledge / guest FAQ — should NOT go through ops planner."""
        q = (query or "").strip()
        if not q:
            return True
        norm = _norm(q)
        if any(p.search(q) or p.search(norm) for p in _FAQ_EXCLUDE_PATTERNS):
            return True
        if OpsCopilotAdapter.is_simple_faq_or_greeting(q):
            return True
        return False

    @staticmethod
    def is_ops_bare_number(query: str) -> bool:
        """3-4 digit bare number that may be a room in ops context."""
        q = (query or "").strip()
        return bool(re.fullmatch(r"\d{3,4}", q))

    @staticmethod
    def is_ops_query(query: str) -> bool:
        q = (query or "").strip()
        if not q:
            return False
        if OpsCopilotAdapter.is_faq_query(q):
            return False
        norm = _norm(q)
        if any(p.search(q) or p.search(norm) for p in _OPS_PATTERNS):
            return True
        # Multi-dept / notify keywords
        if "birim" in norm and any(k in norm for k in ("ulass", "ulas", "haber", "bilgi", "ilet")):
            return True
        # Room + action combo (explicit oda prefix required for bare numbers)
        if re.search(r"\boda\s+\d{2,4}\b", q, re.I) and any(
            k in norm for k in ("gonder", "ticket", "bildir", "temiz", "klima", "teknik", "cozul", "sorun", "durum", "daha once", "daha önce")
        ):
            return True
        # Room mention — staff ops context
        if re.search(r"\boda\s+\d{2,4}\b", q, re.I):
            return True
        # Short follow-up tokens (resolved via session memory in Gateway)
        if norm in ("evet", "tamam", "olur", "klima", "su", "wifi", "bilgi", "rapor", "ticket"):
            return True
        # Bare 3-4 digit only in ops (2-digit like "35" excluded — needs clarification)
        if OpsCopilotAdapter.is_ops_bare_number(q):
            return True
        return False

    def process(
        self,
        query: str,
        *,
        role: Optional[str] = None,
        hotel_id: str = "h1",
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run ops pipeline and return normalized response for ai-service."""
        self._hydrate_gateway_memory(session_id)
        staff_role = self._map_role(role)
        result = self._gateway.process(
            query,
            role=staff_role,
            hotel_id=hotel_id,
            session_id=session_id,
        )
        plan = result.get("plan") or {}
        kinds = plan.get("kind") or []
        tools_used = result.get("tools_used") or []
        resolved = result.get("resolved_query") or {}
        return {
            "answer": result.get("answer", ""),
            "intent": kinds[0].lower() if kinds else "ops_action",
            "department": self._infer_department(tools_used, plan),
            "priority": self._infer_priority(plan),
            "action_required": bool(tools_used) or plan.get("needs_clarification"),
            "sources": ["ops_copilot", "planner", *tools_used],
            "mode": "ops_copilot",
            "entities": self._extract_entities(query, plan, resolved),
            "confidence": plan.get("confidence"),
            "ops_meta": {
                "request_id": result.get("request_id"),
                "plan": plan,
                "tool_results": result.get("tool_results"),
                "tools_used": tools_used,
                "resolved_query": resolved,
                "reasoning": plan.get("reasoning"),
            },
        }

    def _hydrate_gateway_memory(self, session_id: Optional[str]) -> None:
        """Sync ai-service conversation_store into Gateway memory for multi-turn."""
        if not session_id:
            return
        try:
            from app.services.conversation_store import get_conversation_store
            store = get_conversation_store()
            history = store.get_history(session_id)
            mem = self._gateway.memory
            existing_contents = {t.content for t in mem.get_history(session_id)}
            for msg in history:
                content = (msg.get("content") or "").strip()
                role = msg.get("role", "user")
                if content and content not in existing_contents:
                    mem.add_turn(session_id, role, content, msg.get("metadata") or {})
                    existing_contents.add(content)
        except Exception:
            logging.getLogger(__name__).debug("_hydrate_gateway_memory: hata yutuldu", exc_info=True)

    @staticmethod
    def _map_role(role: Optional[str]) -> str:
        mapping = {
            "manager": "duty_manager",
            "guest": "front_office",
            "engineering": "engineering",
            "housekeeping": "housekeeping",
            "gm": "general_manager",
        }
        if not role:
            return "duty_manager"
        return mapping.get(role.lower(), role.lower())

    @staticmethod
    def _infer_department(tools: list[str], plan: dict) -> str:
        for task in plan.get("tasks") or []:
            args = task.get("args") or {}
            if args.get("department"):
                return args["department"]
        if "notify_multi_department" in tools:
            return "Multi-Department"
        if any(t in tools for t in ("create_ticket", "send_notification", "create_work_order")):
            return "Engineering"
        if "get_complaint_trends" in tools or "get_reports" in tools:
            return "DutyManager"
        return "Front Office"

    @staticmethod
    def _infer_priority(plan: dict) -> str:
        for task in plan.get("tasks") or []:
            p = task.get("priority") or (task.get("args") or {}).get("priority")
            if p in ("critical", "high"):
                return p
        return "medium" if plan.get("tasks") else "low"

    @staticmethod
    def _extract_entities(query: str, plan: dict, resolved: Optional[dict] = None) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        if resolved:
            if resolved.get("room_number"):
                entities["room_number"] = resolved["room_number"]
            if resolved.get("issue_category"):
                entities["category"] = resolved["issue_category"]
        m = re.search(r"\boda\s*(\d{2,4})\b", query, re.I)
        if m:
            entities["room_number"] = m.group(1)
        for task in plan.get("tasks") or []:
            args = task.get("args") or {}
            if args.get("room_number"):
                entities["room_number"] = args["room_number"]
            if args.get("category"):
                entities["category"] = args["category"]
        return entities


_adapter: Optional[OpsCopilotAdapter] = None


def get_ops_copilot_adapter() -> OpsCopilotAdapter:
    global _adapter
    if _adapter is None:
        _adapter = OpsCopilotAdapter()
    return _adapter
