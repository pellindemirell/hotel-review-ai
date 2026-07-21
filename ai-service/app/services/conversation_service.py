"""
Konuşma katmanı — personel/yönetici operasyon asistanı persona.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.hotel_knowledge_service import HotelKnowledgeService
from app.services.turkish_nlp_utils import normalize_turkish

_GREETING_PATTERNS = [
    re.compile(r"^(?:selam|sleam|merhaba|hey|slm|sa|hi|hello|hosgeldin|hoş\s*geldin)(?:\s*[!.?]*)?$", re.I),
    re.compile(r"^(?:g[uü]nayd[ıi]n|iyi\s+(?:ak[sş]amlar|g[uü]nler|geceler))(?:\s*[!.?]*)?$", re.I),
]

_HELP_PATTERNS = [
    re.compile(r"bana\s+yard[ıi]m", re.I),
    re.compile(r"yard[ıi]m\s+et", re.I),
    re.compile(r"^yard[ıi]m(?:\s*[!.?]*)?$", re.I),
    re.compile(r"nas[ıi]l\s+yard[ıi]mc[ıi]\s+ol", re.I),
    re.compile(r"ne\s+yapabilir", re.I),
    re.compile(r"neler\s+yapabilir", re.I),
    re.compile(r"sen\s+ne\s+i[sş]e\s+yar", re.I),
]

_SMALL_TALK_PATTERNS = [
    re.compile(r"^(?:nas[ıi]ls[ıi]n|naber|nbr)(?:\s*[!.?]*)?$", re.I),
    re.compile(r"^(?:tamam|ok|peki|anlad[ıi]m|s[üu]per|harika)(?:\s*[!.?]*)?$", re.I),
    re.compile(r"^(?:te[sş]ekk[üu]r(?:ler|ler)?|sa[ğg]ol|sagol|thanks)(?:\s*[!.?]*)?$", re.I),
]

_RAG_EXPLICIT_MARKERS = (
    "gecmis yorum", "geçmiş yorum", "yorumlarda", "yorum analizi",
    "analiz et", "istatistik", "trend raporu", "rapor", "gecmiste", "geçmişte",
    "yorumlardan", "musteri yorum", "müşteri yorum", "review",
)

_HOTEL_KEYWORDS = (
    "oda", "kahvalti", "kahvaltı", "havuz", "spa", "check", "wifi", "klima",
    "temizlik", "havlu", "fatura", "depozito", "otopark", "transfer", "rezervasyon",
    "sorun", "sikayet", "şikayet", "restoran", "servis", "vegan", "helal",
    "yemek", "öğle", "ogle", "akşam", "aksam",
)

_CONVERSATIONAL_INTENTS = frozenset({
    "staff_greeting", "greeting", "help_request", "capabilities", "compliment", "small_talk",
})

_STAFF_OPS_INTENTS = frozenset({
    "complaint_trend", "issue_status_followup", "issue_status_lookup",
    "room_issue_report", "report_room_issue",
    "meal_menu_today", "daily_meal_menu",
    "room_issue", "cross_room_search", "cross_room_problems",
})


class ConversationService:
    """Personel operasyon asistanı — kural tabanlı konuşma."""

    @classmethod
    def is_greeting(cls, query: str) -> bool:
        norm = normalize_turkish((query or "").strip().lower())
        if not norm:
            return False
        return any(p.search(norm) for p in _GREETING_PATTERNS)

    @classmethod
    def is_status_overview(cls, query: str) -> bool:
        norm = normalize_turkish((query or "").strip().lower())
        if not norm:
            return False
        markers = (
            "ne durumdayiz", "ne durumdayız", "durum ozeti", "durum özeti",
            "genel durum", "otel durumu", "durum ne", "nasıl gidiyor", "nasil gidiyor",
        )
        return any(m in norm for m in markers)

    @classmethod
    def is_help_request(cls, query: str) -> bool:
        norm = normalize_turkish((query or "").strip().lower())
        if not norm:
            return False
        return any(p.search(norm) for p in _HELP_PATTERNS)

    @classmethod
    def is_small_talk(cls, query: str) -> bool:
        norm = normalize_turkish((query or "").strip().lower())
        if not norm:
            return False
        return any(p.search(norm) for p in _SMALL_TALK_PATTERNS)

    @classmethod
    def is_conversational(cls, query: str, intent: str = "") -> bool:
        if intent in _CONVERSATIONAL_INTENTS:
            return True
        return cls.is_greeting(query) or cls.is_help_request(query) or cls.is_small_talk(query)

    @classmethod
    def should_block_rag(cls, query: str, intent_data: dict[str, Any]) -> bool:
        intent = intent_data.get("intent", "")
        norm = normalize_turkish((query or "").strip().lower())
        words = norm.split()

        if cls.is_conversational(query, intent):
            return True
        if intent in _CONVERSATIONAL_INTENTS or intent in _STAFF_OPS_INTENTS:
            return True
        if len(words) < 4 and not any(kw in norm for kw in _HOTEL_KEYWORDS):
            return True
        if cls.is_help_request(query):
            return True
        return False

    @classmethod
    def should_allow_rag(cls, query: str) -> bool:
        norm = normalize_turkish((query or "").strip().lower())
        return any(marker in norm for marker in _RAG_EXPLICIT_MARKERS)

    @classmethod
    def format_greeting(cls, hotel_name: Optional[str] = None) -> str:
        name = hotel_name or HotelKnowledgeService.load_profile().get("name", "Otel")
        return (
            f"Merhaba — {name} operasyon asistanıyım.\n\n"
            "Oda sorunları, şikayet trendleri, açık arızalar, departman durumu "
            "ve F&B menü bilgisi konularında yardımcı olurum.\n\n"
            "Örnek: 'oda 102 de sorun var mı', 'bu hafta klima şikayeti', "
            "'geçen haftaki su sorunu çözüldü mü'."
        )

    @classmethod
    def format_help_menu(cls) -> str:
        return HotelKnowledgeService.capabilities_message()

    @classmethod
    def format_small_talk(cls, query: str) -> str:
        norm = normalize_turkish((query or "").strip().lower())
        if re.search(r"te[sş]ekk[üu]r|sa[ğg]ol|thanks", norm):
            return "Rica ederim. Başka bir operasyon sorusu var mı?"
        if re.search(r"nas[ıi]ls[ıi]n|naber", norm):
            return (
                "İyiyim, teşekkürler. Oda durumu, şikayet trendi veya açık arıza "
                "sorgusu için buradayım."
            )
        return "Anladım. Devam etmek için oda numarası, sorun türü veya dönem belirtin."

    @classmethod
    def format_clarification(cls, profile: Optional[dict] = None) -> str:
        _ = profile
        return "Hangi oda veya konu? (ör. oda 788, klima şikayeti, bu hafta rapor)"

    @classmethod
    def format_room_issue_prompt(cls) -> str:
        return (
            "Üzgünüm. Odanızda ne tür bir sorun var? "
            "(klima, su, temizlik, elektrik...)\n\n"
            "İsterseniz oda numaranızı da yazın; hemen kayıt açayım."
        )

    @classmethod
    def resolve_query(
        cls,
        query: str,
        history: Optional[list[dict[str, Any]]] = None,
        session_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Bağlama göre sorguyu zenginleştir."""
        query = (query or "").strip()
        norm = normalize_turkish(query.lower())
        hints: dict[str, Any] = {}
        enriched = query
        ctx = session_context or {}

        if norm in ("neler var", "ne var") and history:
            combined = " ".join(
                m.get("content", "")
                for m in history
                if m.get("role") == "user"
            )
            combined_norm = normalize_turkish(combined.lower())
            if any(k in combined_norm for k in ("vegan", "vejetaryen", "kahvalti", "kahvaltı", "yemek")):
                hints["food_context"] = True
                if "vegan" in combined_norm or "vejetaryen" in combined_norm:
                    hints["vegan_context"] = True
                    enriched = "kahvaltıda vegan neler var"

        if ctx.get("topic") in ("food", "breakfast", "vegan") and norm in ("neler var", "ne var"):
            hints["food_context"] = True
            if ctx.get("topic") == "vegan":
                hints["vegan_context"] = True

        # Ticket akışı: önceki turda oda sorulduysa, sadece numara veya sorun türü gelmiş olabilir
        last_intent = ctx.get("last_intent")
        if last_intent in ("room_issue_report", "report_room_issue"):
            hints["awaiting_room_issue_details"] = True
            room_m = re.search(r"\b(\d{3,4})\b", norm)
            if room_m:
                hints["pending_room"] = room_m.group(1)

        if re.fullmatch(r"\d{2,4}", query.strip()):
            last_room = ctx.get("last_room")
            if last_room and last_room != query.strip():
                hints["last_room"] = last_room
            hints["bare_number"] = query.strip()

        return {"query": enriched, "original": query, "hints": hints}
