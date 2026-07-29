"""
Otel AI Agent — ana orkestratör.
Öncelik: konuşma → yardım → entity/intent → FAQ (sıkı) → şikayet/ABSA → RAG (yalnızca açık analitik).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.absa_service import AbsaService
from app.services.analytics_service import AnalyticsService
from app.services.conversation_service import ConversationService
from app.services.conversation_store import get_conversation_store
from app.services.entity_tracker_service import EntityTrackerService, get_entity_tracker_service
from app.services.hotel_knowledge_service import HotelKnowledgeService
from app.services.intent_service import IntentService
from app.services.rag_service import RagService
from app.services.turkish_nlp_utils import normalize_turkish
from app.services.ops_copilot_adapter import OpsCopilotAdapter, get_ops_copilot_adapter

_COMPLAINT_MARKERS = (
    "şikayet", "sikayet", "berbat", "rezalet", "kötü", "kotu", "memnun değil",
    "memnun degil", "kabul edilemez", "iğrenç", "igrenc",
)

_INTENT_BEFORE_FAQ = frozenset({
    "staff_greeting", "greeting", "help_request", "small_talk", "compliment",
    "capabilities", "services_inquiry", "contextual_neler_var",
    "room_issue", "room_issue_report", "report_room_issue",
    "cross_room_search", "cross_room_problems",
    "room_history", "room_history_no_room", "bare_number",
    "breakfast_menu", "meal_menu_today", "daily_meal_menu", "dirty_room",
    "complaint_trend", "issue_status_followup", "issue_status_lookup",
    "ac_issue", "wifi_issue", "tv_issue", "plumbing_issue",
    "complaint", "request_cleaning", "noise_complaint", "room_service",
})

_STAFF_ANALYTICS_INTENTS = frozenset({
    "complaint_trend", "issue_status_followup", "issue_status_lookup",
    "cross_room_search", "cross_room_problems",
})

# Eski intent adlarını personel kanonik isimlerine çevir
_INTENT_ALIASES = {
    "daily_meal_menu": "meal_menu_today",
    "report_room_issue": "room_issue_report",
    "issue_status_lookup": "issue_status_followup",
    "greeting": "staff_greeting",
}

_RAG_MIN_QUERY_LEN = 12
_RAG_MIN_INTENT_CONFIDENCE = 0.45

_SOP_TEMPLATES = {
    "complaint": (
        "Yaşadığınız sorun için özür dileriz. Talebiniz {department} birimine iletilmiştir. "
        "En kısa sürede size dönüş yapılacaktır."
    ),
    "technical": (
        "Yaşadığınız teknik sorun için özür dileriz. Teknik ekibimize hemen bilgi iletiyoruz. "
        "Mümkün olan en kısa sürede odanıza müdahale edilecektir."
    ),
    "housekeeping": (
        "Talebiniz için teşekkür ederiz. Kat hizmetleri ekibimiz en kısa sürede odanıza yönlendirilecektir."
    ),
    "dirty_room": (
        "Odanızın temizlik durumu için özür dileriz. Kat hizmetleri ekibimiz acil olarak "
        "bilgilendirildi; en kısa sürede odanız temizlenecektir."
    ),
    "general_action": (
        "Talebiniz kaydedildi. {department} ekibimiz bilgilendirildi; kısa süre içinde size yardımcı olacaklardır."
    ),
}


class HotelAgentService:
    """Unified Hotel Operations AI Agent."""

    @classmethod
    def _profile_answer_for_entity(cls, entity: dict, profile: dict, query: str) -> Optional[str]:
        norm = normalize_turkish(query.lower())
        ekey = (entity.get("entity_key") or entity.get("entity_id") or "").lower()
        if ekey in ("havuz", "havuz_alani") or "havuz" in norm:
            pool = profile.get("pool", {})
            if any(k in norm for k in ("saat", "kaçta", "ne zaman", "açık", "acik", "kapan", "bitiyor")):
                return f"Havuz saatleri {pool.get('hours', '08:00-20:00')}. Çocuk havuzu: {'Mevcut' if pool.get('children_pool') else 'Yok'}."
        if ekey in ("spa", "spa_alani") or ("spa" in norm and "saat" in norm):
            spa = profile.get("spa", {})
            return f"Spa saatleri {spa.get('hours', '10:00-22:00')}."
        if ekey in ("restoran", "restaurant") or any(k in norm for k in ("kahvaltı", "kahvalti", "restoran")):
            bf = profile.get("breakfast", {})
            return f"Kahvaltı {bf.get('hours', '07:00-10:30')}. Vegan: {'Evet' if bf.get('vegan') else 'Hayır'}."
        if "wifi" in norm or "internet" in norm:
            if any(k in norm for k in ("çalışm", "calism", "yok", "sorun", "kesik", "çekm", "kop")):
                return None
            wifi = profile.get("wifi", {})
            return f"WiFi ücretsizdir. Şifre: {wifi.get('password_location', 'oda kartı / resepsiyon')}."
        return None

    @classmethod
    def _breakfast_menu_answer(cls, profile: dict) -> str:
        bf = profile.get("breakfast", {})
        hours = bf.get("hours", "07:00-10:30")
        location = bf.get("location", "Ana Restoran")
        items = bf.get("menu_items") or [
            "Peynir ve zeytin çeşitleri",
            "Sıcak/soğuk omlet ve yumurta çeşitleri",
            "Reçel, bal, tereyağı",
            "Taze meyve ve sebze",
            "Sıcak yemekler (menemen, sucuk-yumurta)",
            "Glutensiz ekmek ve vegan süt alternatifleri",
        ]
        item_lines = "\n".join(f"- {item}" for item in items)
        vegan = "Evet" if bf.get("vegan") else "Hayır"
        gluten = "Evet" if bf.get("gluten_free") else "Hayır"
        return (
            f"Kahvaltı {hours} arası {location}'da açık büfe olarak servis edilir.\n\n"
            f"**Çeşitler:**\n{item_lines}\n\n"
            f"Vegan seçenek: {vegan} | Glutensiz seçenek: {gluten}"
        )

    @classmethod
    def _meal_menu_today_answer(cls, profile: dict, query: str = "") -> str:
        return HotelKnowledgeService.format_meal_menu_today(profile, query)

    @classmethod
    def _room_issue_report_answer(cls, query: str, intent_data: dict) -> str:
        """Personel ticket akışı — kısa netleştirme, misafir SOP değil."""
        room = (intent_data.get("entities") or {}).get("room_number")
        issue_type = EntityTrackerService.extract_issue_type(query)
        if room and issue_type:
            return (
                f"Oda {room} — {issue_type} kaydı açılabilir. "
                "Onaylıyor musunuz? (veya ek detay yazın)"
            )
        if room:
            return (
                f"Oda {room} için ne sorunu? "
                "(klima / su / wifi / temizlik / elektrik…)\n"
                "Kısaca yazın, ticket açayım."
            )
        if issue_type:
            return (
                f"{issue_type.title()} sorunu — hangi oda?\n"
                "Örnek: 'oda 204' yazmanız yeterli."
            )
        return ConversationService.format_room_issue_prompt()

    @classmethod
    def _should_use_faq(
        cls,
        query: str,
        faq_result: dict,
        intent_data: dict,
        entity: Optional[dict],
    ) -> bool:
        if not faq_result.get("answer"):
            return False
        faq_score = faq_result.get("score", 0)
        intent = intent_data.get("intent", "")
        intent_conf = intent_data.get("confidence", 0)

        if intent in _INTENT_BEFORE_FAQ and intent_conf >= 0.4:
            return False
        if entity and EntityTrackerService.is_entity_query(query):
            return False
        if EntityTrackerService.is_cross_room_query(query):
            return False
        if HotelKnowledgeService.is_blocked_faq_match(query, faq_result):
            return False
        if intent_conf > faq_score:
            return False
        if faq_score < 0.75:
            return False
        return HotelKnowledgeService.has_keyword_overlap(query, faq_result)

    @classmethod
    def _should_use_rag(cls, query: str, intent_data: dict) -> bool:
        """RAG yalnızca açık geçmiş yorum / analitik sorularında."""
        intent = intent_data.get("intent", "")
        conf = intent_data.get("confidence", 0)
        norm = normalize_turkish(query.lower().strip())

        if ConversationService.should_block_rag(query, intent_data):
            return False
        if not ConversationService.should_allow_rag(query):
            return False
        if intent in _INTENT_BEFORE_FAQ:
            return False
        if EntityTrackerService.is_bare_room_number(query):
            return False
        if len(norm) < 4:
            return False
        if intent == "general_inquiry" and len(norm.split()) <= 2 and conf < _RAG_MIN_INTENT_CONFIDENCE:
            return False
        if intent == "general_inquiry" and len(norm) < _RAG_MIN_QUERY_LEN and conf < 0.55:
            return False
        if re.fullmatch(r"\d{2,4}", norm):
            return False
        return True

    @classmethod
    def _should_clarify(cls, query: str, intent_data: dict) -> bool:
        if ConversationService.is_conversational(query, intent_data.get("intent", "")):
            return False
        norm = normalize_turkish(query.lower().strip())
        if norm in ("neler var", "ne var"):
            return False
        if EntityTrackerService.is_bare_room_number(query):
            return True
        intent = intent_data.get("intent", "")
        conf = intent_data.get("confidence", 0)
        if intent == "general_inquiry" and len(norm.split()) <= 3 and conf < 0.5:
            return True
        return False

    @classmethod
    def _clarification_for_vague_query(cls, query: str, profile: dict) -> Optional[str]:
        if ConversationService.is_conversational(query):
            return None
        norm = normalize_turkish(query.lower().strip())
        if norm in ("neler var", "ne var"):
            return HotelKnowledgeService.format_services_list(profile)
        if EntityTrackerService.is_bare_room_number(query):
            num = query.strip()
            return f"Oda {num} — ne sormak istiyorsunuz? (sorun geçmişi / ticket / durum)"
        if cls._should_clarify(query, IntentService.detect(query)):
            return ConversationService.format_clarification(profile)
        return None

    @classmethod
    def _apply_sop_tone(cls, answer: str, intent_data: dict, is_complaint: bool = False) -> str:
        dept = intent_data.get("department", "Front Office")
        intent = intent_data.get("intent", "")

        if is_complaint or intent == "complaint":
            prefix = _SOP_TEMPLATES["complaint"].format(department=dept)
            if not answer.startswith("Yaşadığınız"):
                return f"{prefix}\n\n{answer}"
            return answer

        if intent == "dirty_room":
            prefix = _SOP_TEMPLATES["dirty_room"]
            if "özür" not in answer.lower():
                return f"{prefix}\n\n{answer}"

        if intent in ("ac_issue", "wifi_issue", "tv_issue", "plumbing_issue"):
            if "özür" not in answer.lower():
                return f"{_SOP_TEMPLATES['technical']}\n\n{answer}"

        if intent in ("request_towel", "request_cleaning", "dirty_room") and "teşekkür" not in answer.lower() and "özür" not in answer.lower():
            return f"{_SOP_TEMPLATES['housekeeping']}\n\n{answer}"

        if intent_data.get("action_required") and "kaydedildi" not in answer.lower() and "özür" not in answer.lower():
            return _SOP_TEMPLATES["general_action"].format(department=dept) + f"\n\n{answer}"

        return answer

    @classmethod
    def _build_response(
        cls,
        *,
        answer: str,
        intent_data: dict,
        mode: str,
        sources: list[str],
        entities: Optional[dict] = None,
        extra: Optional[dict] = None,
        is_complaint: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": answer,
            "intent": intent_data["intent"],
            "department": intent_data["department"],
            "priority": intent_data["priority"],
            "action_required": intent_data["action_required"],
            "entities": entities or intent_data.get("entities", {}),
            "sources": sources,
            "mode": mode,
            "confidence": intent_data.get("confidence", 0),
        }
        if extra:
            payload.update(extra)
        return payload

    @classmethod
    async def process_query(
        cls,
        query: str,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {
                "answer": "Lütfen bir soru veya talep yazın.",
                "intent": "empty",
                "department": "Front Office",
                "priority": "low",
                "action_required": False,
                "sources": [],
                "mode": "empty",
            }

        conv_store = get_conversation_store()
        history = conv_store.get_history(session_id) if session_id else []
        session_ctx = conv_store.get_context(session_id) if session_id else {}
        resolved = ConversationService.resolve_query(query, history, session_ctx)
        query_for_routing = resolved["query"]
        context_hints = resolved.get("hints", {})

        profile = HotelKnowledgeService.load_profile()
        intent_data = IntentService.detect(query_for_routing, history=history)
        # Kanonik intent adları (eski alias'ları birleştir)
        canon = _INTENT_ALIASES.get(intent_data.get("intent", ""), intent_data.get("intent", ""))
        if canon != intent_data.get("intent"):
            intent_data = {**intent_data, "intent": canon}
        norm = normalize_turkish(query.lower())
        # Konu/trend / durum soruları misafir şikayet SOP'u değildir
        is_analytics_complaint = (
            intent_data["intent"] in _STAFF_ANALYTICS_INTENTS
            or EntityTrackerService.is_complaint_trend_query(query_for_routing)
            or EntityTrackerService.is_issue_status_followup_query(query_for_routing)
        )
        is_complaint = any(m in norm for m in _COMPLAINT_MARKERS) and not is_analytics_complaint
        faq_result = HotelKnowledgeService.answer_faq(query_for_routing)

        entity_svc = get_entity_tracker_service()
        entity = EntityTrackerService.extract_entity(query_for_routing)
        sources: list[str] = []

        def _finalize(response: dict[str, Any]) -> dict[str, Any]:
            if session_id:
                conv_store.record_turn(
                    session_id,
                    query,
                    response.get("answer", ""),
                    {
                        "intent": response.get("intent", intent_data.get("intent")),
                        "entities": response.get("entities") or intent_data.get("entities", {}),
                        "mode": response.get("mode"),
                    },
                )
            return response

        # 0) Selamlama — personel operasyon asistanı
        if (
            ConversationService.is_greeting(query)
            or intent_data["intent"] in ("staff_greeting", "greeting")
        ):
            hotel_name = (profile.get("hotel") or {}).get("name") or profile.get("name")
            return _finalize(cls._build_response(
                answer=ConversationService.format_greeting(hotel_name),
                intent_data={**intent_data, "intent": "staff_greeting"},
                mode="conversational",
                sources=["greeting"],
            ))

        # 0b) Genel durum özeti — ops copilot
        if ConversationService.is_status_overview(query):
            ops_result = get_ops_copilot_adapter().process(
                query_for_routing,
                role=role or "manager",
                hotel_id="h1",
                session_id=session_id,
            )
            return _finalize(ops_result)

        # 1) Yardım / yetenekler — asla RAG
        if (
            ConversationService.is_help_request(query)
            or intent_data["intent"] in ("help_request", "capabilities")
        ):
            return _finalize(cls._build_response(
                answer=ConversationService.format_help_menu(),
                intent_data={**intent_data, "intent": "help_request" if intent_data["intent"] != "capabilities" else "capabilities"},
                mode="static_help",
                sources=["capabilities"],
            ))

        # 2b) Ops Copilot — planner-worthy staff ops (notify, ticket, trend, report, multi-turn)
        ops_adapter = get_ops_copilot_adapter()
        _ops_followup = session_id and (
            re.fullmatch(r"\d{3,4}", query_for_routing.strip())
            or normalize_turkish(query_for_routing.lower().strip()) in (
                "evet", "tamam", "olur", "klima", "su", "wifi",
                "bilgi", "rapor", "ticket",
            )
        )
        if (
            not OpsCopilotAdapter.is_faq_query(query)
            and (
                OpsCopilotAdapter.is_ops_query(query_for_routing)
                or _ops_followup
                or EntityTrackerService.is_room_history_query(query_for_routing)
                or EntityTrackerService.is_issue_status_followup_query(query_for_routing)
            )
        ):
            ops_result = ops_adapter.process(
                query_for_routing,
                role=role or "manager",
                hotel_id="h1",
                session_id=session_id,
            )
            return _finalize(ops_result)

        # 2) Küçük sohbet / teşekkür
        if (
            ConversationService.is_small_talk(query)
            or intent_data["intent"] in ("small_talk", "compliment")
        ):
            return _finalize(cls._build_response(
                answer=ConversationService.format_small_talk(query),
                intent_data={**intent_data, "intent": "small_talk"},
                mode="conversational",
                sources=["small_talk"],
            ))

        # Bağlamsal "neler var" — önceki turda yemek/vegan konusu
        orig_norm = normalize_turkish(query.lower().strip())
        if orig_norm in ("neler var", "ne var"):
            food_ctx = (
                context_hints.get("food_context")
                or (session_id and conv_store.has_food_context(session_id))
            )
            if food_ctx:
                answer = cls._breakfast_menu_answer(profile)
                if context_hints.get("vegan_context") or (session_id and conv_store.has_vegan_context(session_id)):
                    answer = (
                        "**Vegan kahvaltı seçenekleri:**\n\n"
                        + answer
                        + "\n\nVegan seçeneklerimiz arasında bitkisel süt alternatifleri, "
                        "taze meyve-sebze, reçel, zeytin ve glutensiz ekmek bulunmaktadır."
                    )
                return _finalize(cls._build_response(
                    answer=answer,
                    intent_data={**intent_data, "intent": "breakfast_menu"},
                    mode="hotel_knowledge",
                    sources=["hotel_profile", "conversation_context"],
                ))

        # Otel hizmetleri listesi
        if intent_data["intent"] == "services_inquiry":
            return _finalize(cls._build_response(
                answer=HotelKnowledgeService.format_services_list(profile),
                intent_data=intent_data,
                mode="hotel_knowledge",
                sources=["hotel_profile"],
            ))

        # Bugün yemek / öğle-akşam menüsü (kahvaltı değil)
        if intent_data["intent"] in ("meal_menu_today", "daily_meal_menu") or (
            ("yemekte" in norm or re.search(r"(?:[öo]ğ?le|ak[sş]am)\s+yeme", norm))
            and "kahvalt" not in norm
        ):
            answer = cls._meal_menu_today_answer(profile, query_for_routing)
            return _finalize(cls._build_response(
                answer=answer,
                intent_data={**intent_data, "intent": "meal_menu_today", "department": "F&B"},
                mode="hotel_knowledge",
                sources=["hotel_profile", "intent_routing"],
            ))

        # Misafir oda sorunu bildirimi — empati + netleştirme (uzun menü yok)
        if intent_data["intent"] in ("room_issue_report", "report_room_issue") or re.search(
            r"odamda\s+(?:bir\s+)?(?:sorun|problem|ar[ıi]za)", norm
        ):
            answer = cls._room_issue_report_answer(query_for_routing, intent_data)
            return _finalize(cls._build_response(
                answer=answer,
                intent_data={
                    **intent_data,
                    "intent": "room_issue_report",
                    "department": "Engineering",
                    "action_required": True,
                    "priority": "high",
                },
                mode="intent_action",
                sources=["intent_routing"],
                entities=intent_data.get("entities", {}),
            ))

        # Intent öncelikli: complaint_trend vs issue_status_followup
        if intent_data["intent"] in ("issue_status_followup", "issue_status_lookup") or (
            EntityTrackerService.is_issue_status_followup_query(query_for_routing)
            and intent_data["intent"] != "complaint_trend"
        ):
            status_answer = entity_svc.format_issue_status_followup_answer(query_for_routing)
            if status_answer:
                return _finalize(cls._build_response(
                    answer=status_answer,
                    intent_data={
                        **intent_data,
                        "intent": "issue_status_followup",
                        "department": "Engineering",
                        "action_required": False,
                    },
                    mode="entity_tracker",
                    sources=["entity_tracker"],
                ))

        # Şikayet trendi / konu bazlı analitik (misafir SOP değil)
        if intent_data["intent"] == "complaint_trend" or (
            EntityTrackerService.is_complaint_trend_query(query_for_routing)
            and intent_data["intent"] not in ("issue_status_followup", "issue_status_lookup")
        ):
            trend_answer = entity_svc.format_complaint_trend_answer(query_for_routing)
            if not trend_answer:
                trend_answer = entity_svc.format_cross_room_chat_answer(query_for_routing)
            if not trend_answer:
                analytics_fallback = AnalyticsService.chatbot_analytics_answer(
                    query_for_routing, role=role or "manager"
                )
                if analytics_fallback:
                    trend_answer = analytics_fallback
            if trend_answer:
                return _finalize(cls._build_response(
                    answer=trend_answer,
                    intent_data={
                        **intent_data,
                        "intent": "complaint_trend",
                        "department": "Engineering",
                        "action_required": False,
                    },
                    mode="analytics" if "İstatistik" in trend_answer or "istatistik" in trend_answer.lower() else "entity_tracker",
                    sources=["entity_tracker", "analytics"],
                ))

        # 2) Bağlamsal "neler var" — F&B veya genel hizmetler
        if intent_data["intent"] == "contextual_neler_var":
            food_ctx = (
                EntityTrackerService.is_food_context_query(query_for_routing)
                or context_hints.get("food_context")
                or (session_id and conv_store.has_food_context(session_id))
            )
            if food_ctx:
                answer = cls._breakfast_menu_answer(profile)
                if context_hints.get("vegan_context") or (session_id and conv_store.has_vegan_context(session_id)):
                    answer = (
                        "**Vegan kahvaltı seçenekleri:**\n\n"
                        + answer
                        + "\n\nVegan seçeneklerimiz arasında bitkisel süt alternatifleri, "
                        "taze meyve-sebze, reçel, zeytin ve glutensiz ekmek bulunmaktadır."
                    )
                intent_data = {**intent_data, "intent": "breakfast_menu"}
            else:
                answer = HotelKnowledgeService.format_services_list(profile)
            return _finalize(cls._build_response(
                answer=answer,
                intent_data=intent_data,
                mode="hotel_knowledge",
                sources=["hotel_profile"],
            ))

        # 3) Çıplak oda numarası — netleştirme, RAG yok
        if intent_data["intent"] == "bare_number" or EntityTrackerService.is_bare_room_number(query):
            num = query.strip()
            last_room = context_hints.get("last_room") or (conv_store.get_last_room(session_id) if session_id else None)
            pending = session_ctx.get("pending_clarification") if session_ctx else None
            # 2-digit or ambiguous 3-4 digit without context → clarification
            if re.fullmatch(r"\d{2}", num) or (re.fullmatch(r"\d{3,4}", num) and not last_room and not pending):
                clarify = cls._clarification_for_vague_query(query, profile)
                return _finalize(cls._build_response(
                    answer=clarify or f"Hangi oda ({num}) hakkında bilgi istiyorsunuz?",
                    intent_data={**intent_data, "intent": "bare_number"},
                    mode="clarification",
                    sources=["clarification"],
                    entities={"room_number": num},
                ))
            room_entity = {
                "entity_id": f"room_{num}",
                "entity_key": num,
                "entity_label": f"Oda {num}",
                "entity_type": "room",
            }
            history_q = f"oda {num} de sorun var mı"
            entity_answer = entity_svc.format_entity_chat_answer(history_q)
            if entity_answer and "kayıtlı sorun" not in entity_answer.lower():
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=entity_answer,
                    intent_data={**intent_data, "intent": "room_issue"},
                    mode="entity_tracker",
                    sources=sources,
                    entities={"room_number": num, "entity": room_entity},
                ))
            clarify = cls._clarification_for_vague_query(query, profile)
            return _finalize(cls._build_response(
                answer=clarify or f"Hangi oda ({num}) hakkında bilgi istiyorsunuz?",
                intent_data={**intent_data, "intent": "bare_number"},
                mode="clarification",
                sources=["clarification"],
                entities={"room_number": num},
            ))

        # 4) Oda geçmişi — oda numarası ile
        if intent_data["intent"] == "room_history" or EntityTrackerService.is_room_history_query(query_for_routing):
            entity_answer = entity_svc.format_entity_chat_answer(query_for_routing)
            if entity_answer:
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=entity_answer,
                    intent_data={**intent_data, "intent": "room_history"},
                    mode="entity_tracker",
                    sources=sources,
                    entities=intent_data.get("entities", {}),
                ))

        # 5) Oda geçmişi — oda numarası yok
        if intent_data["intent"] == "room_history_no_room":
            summary = entity_svc.format_recent_issues_summary()
            answer = (
                "Hangi oda hakkında bilgi almak istediğinizi belirtir misiniz?\n\n"
                f"{summary}"
            )
            return _finalize(cls._build_response(
                answer=answer,
                intent_data=intent_data,
                mode="entity_tracker",
                sources=["entity_tracker"],
            ))

        # 6) Oda + sorun/kirli/klima → entity tracker (oda bazlı)
        if (
            entity
            and entity.get("entity_type") == "room"
            and EntityTrackerService.is_entity_query(query_for_routing)
        ):
            entity_answer = entity_svc.format_entity_chat_answer(query_for_routing)
            if entity_answer:
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=entity_answer,
                    intent_data=intent_data,
                    mode="entity_tracker",
                    sources=sources,
                    entities={**intent_data.get("entities", {}), "entity": entity},
                ))

        # 7) Çapraz oda sorun araması
        cross_intents = ("cross_room_search", "cross_room_problems")
        if EntityTrackerService.is_cross_room_query(query_for_routing) or intent_data["intent"] in cross_intents:
            cross_answer = entity_svc.format_cross_room_chat_answer(query_for_routing)
            if cross_answer:
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=cross_answer,
                    intent_data={**intent_data, "intent": "cross_room_problems", "department": "Engineering"},
                    mode="entity_tracker",
                    sources=sources,
                ))

        # 8) Diğer entity sorguları (havuz, restoran vb.)
        if entity and EntityTrackerService.is_entity_query(query_for_routing):
            entity_answer = entity_svc.format_entity_chat_answer(query_for_routing)
            if entity_answer:
                dept = intent_data["department"]
                if entity.get("entity_type") == "area" and entity.get("entity_id") in ("havuz_alani", "spa_alani"):
                    dept = "Spa"
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=entity_answer,
                    intent_data=intent_data,
                    mode="entity_tracker",
                    sources=sources,
                    entities={**intent_data.get("entities", {}), "entity": entity},
                ))

        # 9) Kahvaltı menüsü / çeşitler (yalnızca kahvaltı)
        if intent_data["intent"] == "breakfast_menu":
            answer = cls._breakfast_menu_answer(profile)
            sources.extend(["hotel_profile", "intent_routing"])
            return _finalize(cls._build_response(
                answer=answer,
                intent_data=intent_data,
                mode="hotel_knowledge",
                sources=sources,
            ))

        # 10) Kirli oda şikayeti
        if intent_data["intent"] == "dirty_room":
            answer = cls._apply_sop_tone(
                "Oda temizlik durumunuz kayıt altına alındı. Kat hizmetleri ekibi yönlendirildi.",
                intent_data,
                is_complaint,
            )
            entity_svc.register_from_comment(query)
            sources.extend(["intent_routing", "entity_tracker"])
            return _finalize(cls._build_response(
                answer=answer,
                intent_data={**intent_data, "action_required": True, "priority": "high"},
                mode="intent_action",
                sources=sources,
                entities=intent_data.get("entities", {}),
            ))

        # 11) Entity issue kaydı (oda + klima/kirli vb.)
        if entity:
            profile_answer = cls._profile_answer_for_entity(entity, profile, query_for_routing)
            if profile_answer:
                answer = cls._apply_sop_tone(profile_answer, intent_data, is_complaint)
                sources.extend(["hotel_profile", "entity_tracker"])
                return _finalize(cls._build_response(
                    answer=answer,
                    intent_data=intent_data,
                    mode="entity_knowledge",
                    sources=sources,
                    entities={**intent_data.get("entities", {}), "entity": entity},
                ))

            issue_type = EntityTrackerService.extract_issue_type(query_for_routing)
            if issue_type and entity.get("entity_type") == "room":
                dept = "Engineering" if issue_type in (
                    "klima", "priz", "wifi", "tv", "lamba", "duş", "minibar", "kapı", "asansör"
                ) else "Housekeeping"
                answer = cls._apply_sop_tone(
                    f"{entity['entity_label']} için {issue_type} talebiniz kaydedildi. "
                    f"İlgili birim ({dept}) bilgilendiriliyor.",
                    {**intent_data, "department": dept},
                    is_complaint,
                )
                entity_svc.register_from_comment(query)
                sources.append("entity_tracker")
                return _finalize(cls._build_response(
                    answer=answer,
                    intent_data={**intent_data, "department": dept, "action_required": True, "priority": "high"},
                    mode="entity_room_issue",
                    sources=sources,
                    entities={**intent_data.get("entities", {}), "entity": entity},
                ))

        # 12) FAQ — sıkı eşik
        if cls._should_use_faq(query_for_routing, faq_result, intent_data, entity):
            answer = cls._apply_sop_tone(faq_result["answer"], intent_data, is_complaint)
            sources.extend(faq_result.get("sources", ["hotel_faq"]))
            return _finalize(cls._build_response(
                answer=answer,
                intent_data=intent_data,
                mode="hotel_knowledge",
                sources=sources,
                extra={"matched_question": faq_result.get("matched_question"), "confidence": faq_result.get("score", 0)},
            ))

        # 13) Action-required operational intents
        if intent_data["action_required"] and intent_data["confidence"] >= 0.4:
            dept_key = intent_data.get("department_key", "resepsiyon")
            dept_info = HotelKnowledgeService.get_department_info(dept_key)
            sop = dept_info.get("sop_summary", "") if dept_info.get("found") else ""
            answer = cls._apply_sop_tone(
                sop or f"{intent_data['intent']} talebiniz alındı.",
                intent_data,
                is_complaint,
            )
            sources.append("intent_routing")
            if dept_info.get("found"):
                sources.append("department_sop")
            return _finalize(cls._build_response(
                answer=answer,
                intent_data=intent_data,
                mode="intent_action",
                sources=sources,
            ))

        # 14) Complaint / ABSA analysis
        if is_complaint or intent_data["intent"] == "complaint":
            absa = AbsaService.analyze(query)
            absa_dict = AbsaService.to_dict(absa)
            aspects = absa_dict.get("aspects", [])
            if aspects:
                top = aspects[0]
                answer = (
                    f"Yaşadığınız sorun için özür dileriz. "
                    f"{top.get('department', 'İlgili birim')} ekibimize bilgi iletiyoruz. "
                    f"Konu: {top.get('aspect', 'genel')}. "
                    f"Önerilen aksiyon: {top.get('suggestion', 'En kısa sürede dönüş yapılacaktır.')}"
                )
                sources.extend(["absa", "analytics"])
                return _finalize(cls._build_response(
                    answer=answer,
                    intent_data={**intent_data, "intent": "complaint", "action_required": True, "priority": "high"},
                    mode="absa_complaint",
                    sources=sources,
                    extra={"absa": absa_dict},
                ))

        # 15) Yönetici dashboard / analitik sorguları
        analytics_answer = AnalyticsService.chatbot_analytics_answer(query_for_routing, role=role)
        if analytics_answer and (
            role == "manager"
            or ConversationService.should_allow_rag(query_for_routing)
            or any(k in norm for k in ("istatistik", "dashboard", "rapor", "oran"))
        ):
            return _finalize(cls._build_response(
                answer=analytics_answer,
                intent_data={**intent_data, "intent": "analytics", "department": "Management"},
                mode="analytics",
                sources=["analytics", "review_store"],
            ))

        # 16) Belirsiz/kısa sorgu — netleştirme, RAG öncesi
        if not cls._should_use_rag(query_for_routing, intent_data):
            if cls._should_clarify(query, intent_data):
                clarify = cls._clarification_for_vague_query(query, profile)
                if clarify:
                    return _finalize(cls._build_response(
                        answer=clarify,
                        intent_data={**intent_data, "intent": "clarification"},
                        mode="clarification",
                        sources=["clarification"],
                    ))
            # RAG engellendi — profil/FAQ son çare
            if faq_result.get("answer") and faq_result.get("score", 0) >= 0.55:
                answer = cls._apply_sop_tone(faq_result["answer"], intent_data, is_complaint)
                sources.extend(faq_result.get("sources", ["hotel_faq"]))
                return _finalize(cls._build_response(
                    answer=answer,
                    intent_data=intent_data,
                    mode="hotel_knowledge",
                    sources=sources,
                ))
            return _finalize(cls._build_response(
                answer=ConversationService.format_clarification(profile),
                intent_data={**intent_data, "intent": "clarification"},
                mode="clarification",
                sources=["clarification"],
            ))

        # 17) RAG — yalnızca açık geçmiş yorum / analitik sorular
        rag_result = await RagService.chat_with_rag(query_for_routing, api_key=api_key)
        answer = rag_result.get("response", "")
        mode = rag_result.get("mode", "rag")

        if faq_result.get("answer") and faq_result.get("score", 0) >= 0.6 and not HotelKnowledgeService.is_blocked_faq_match(query_for_routing, faq_result):
            answer = faq_result["answer"] + "\n\n---\n" + answer
            sources.extend(faq_result.get("sources", []))
            mode = "hotel_knowledge+rag"

        sources.append(f"rag:{mode}")

        return _finalize(cls._build_response(
            answer=answer,
            intent_data=intent_data,
            mode=mode,
            sources=sources,
            extra={
                "rag_meta": {
                    "indexed_records": rag_result.get("indexed_records"),
                    "matches_found": rag_result.get("matches_found"),
                    "data_source": rag_result.get("data_source"),
                },
            },
        ))


def get_hotel_agent_service() -> HotelAgentService:
    return HotelAgentService()
