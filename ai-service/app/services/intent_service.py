"""
Otel operasyonları intent tespiti ve departman yönlendirme.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.turkish_nlp_utils import normalize_turkish

# (intent_id, department, priority, action_required, keywords, entity_extractors)
_INTENT_RULES: list[dict[str, Any]] = [
    {
        "intent": "staff_greeting",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "selam", "sleam", "merhaba", "hey", "slm", "sa", "hi", "hello",
            "günaydın", "gunaydin", "iyi akşamlar", "iyi aksamlar", "iyi günler",
        ],
        "patterns": [
            r"^(?:selam|sleam|merhaba|hey|slm|sa|hi|hello)(?:\s*[!.?]*)?$",
            r"^(?:g[uü]nayd[ıi]n|iyi\s+(?:ak[sş]am|g[uü]nler|geceler))(?:\s*[!.?]*)?$",
        ],
    },
    {
        "intent": "help_request",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "bana yardım", "bana yardim", "yardım et", "yardim et", "yardımcı ol",
            "yardimci ol", "yardım", "yardim",
        ],
        "patterns": [
            r"bana\s+yard[ıi]m",
            r"yard[ıi]m\s+et",
            r"^yard[ıi]m(?:\s*[!.?]*)?$",
        ],
    },
    {
        "intent": "small_talk",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": ["nasılsın", "nasilsin", "naber", "tamam", "peki", "anladım"],
        "patterns": [
            r"^(?:nas[ıi]ls[ıi]n|naber|nbr)(?:\s*[!.?]*)?$",
            r"^(?:tamam|ok|peki|anlad[ıi]m)(?:\s*[!.?]*)?$",
        ],
    },
    {
        "intent": "capabilities",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "nasıl yardımcı olabilirsin", "nasil yardimci olabilirsin", "ne yapabilirsin",
            "neler yapabilirsin", "ne işe yarıyorsun", "bot ne yapar", "yeteneklerin",
            "neler sorabilirim", "help", "yardım menüsü",
        ],
        "patterns": [
            r"nas[ıi]l\s+yard[ıi]mc[ıi]\s+ol",
            r"ne\s+yapabilir",
            r"sen\s+ne\s+i[sş]e\s+yar",
        ],
    },
    {
        "intent": "services_inquiry",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "hangi hizmetler var", "otelde neler var", "hizmetler neler",
            "tesisler neler", "otel imkanlari", "otel imkânları", "neler sunuluyor",
            "otelde ne var", "facilities",
        ],
        "patterns": [
            r"hangi\s+hizmet",
            r"otelde\s+neler\s+var",
            r"hizmetler\s+neler",
        ],
    },
    {
        "intent": "contextual_neler_var",
        "department": "F&B",
        "priority": "low",
        "action_required": False,
        "keywords": ["neler var", "ne var", "neler sunuluyor"],
        "patterns": [r"^neler\s+var$", r"^ne\s+var$"],
    },
    {
        "intent": "cross_room_problems",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": [
            "odalarda ne problemi", "odalarda ne sorunu", "hangi odalarda sorun",
            "hangi odalarda problem", "açık sorunlu odalar", "acik sorunlu odalar",
        ],
        "patterns": [
            r"odalarda.*(?:proble|sorun)",
            r"hangi\s*odalarda.*(?:sorun|proble)",
            r"(?:açık|acik)\s+sorun.*oda",
        ],
    },
    {
        "intent": "room_history",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": [],
        "patterns": [
            r"oda\s+\d{3,4}.*(?:daha\s+once|daha\s+önce|gecmis|geçmiş|sorun\s+olmus|sorun\s+olmuş)",
            r"\d{3,4}.*(?:daha\s+once|daha\s+önce).*(?:sorun|sikayet)",
            r"(?:daha\s+once|daha\s+önce).*(?:sorun|sikayet).*\d{3,4}",
        ],
    },
    {
        "intent": "room_history_no_room",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": [
            "daha once sorun olmus mu", "daha önce sorun olmuş mu",
            "daha once problem olmus mu", "gecmiste sorun var mi",
        ],
        "patterns": [
            r"daha\s+once.*sorun\s+olmus",
            r"daha\s+önce.*sorun\s+olmuş",
            r"gecmis.*sorun",
        ],
    },
    {
        "intent": "bare_number",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": [],
        "patterns": [r"^\d{2,4}$"],
    },
    {
        "intent": "meal_menu_today",
        "department": "F&B",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "bugün yemekte", "bugun yemekte", "yemekte neler", "yemekte ne var",
            "öğle yemeği", "ogle yemegi", "akşam yemeği", "aksam yemegi",
            "bugün menü", "bugun menu", "öğle menü", "akşam menü",
            "öğle yemekte", "akşam yemekte",
        ],
        "patterns": [
            r"bug[uü]n\s+yemekte",
            r"yemekte\s+(?:neler|ne\s+var)",
            r"[öo]ğ?le\s+yeme[ğg]i",
            r"ak[sş]am\s+yeme[ğg]i",
            r"bug[uü]n\s+(?:[öo]ğ?le|ak[sş]am|yemek).*(?:ne|men[uü]|neler)",
            r"(?:[öo]ğ?le|ak[sş]am)\s+(?:men[uü]|yemek).*(?:ne|neler)",
        ],
    },
    {
        "intent": "room_issue_report",
        "department": "Engineering",
        "priority": "high",
        "action_required": True,
        "keywords": [
            "odamda sorun", "odamda problem", "odamda arıza", "odamda ariza",
            "odamda bir sorun", "odamda bir problem", "odamda bir arıza",
            "bir sorun var", "sorun bildir", "arıza bildir",
        ],
        "patterns": [
            r"odamda\s+(?:bir\s+)?(?:sorun|problem|ar[ıi]za)",
            r"odamda\s+.*(?:sorun|problem|ar[ıi]za)\s+var",
            r"(?:odamda|odamızda|odamizda)\s+(?:bir\s+)?(?:sorun|problem|ar[ıi]za)",
            r"(?:bir\s+)?(?:sorun|problem|ar[ıi]za)\s+(?:bildir|a[cç]|kaydet)",
        ],
    },
    {
        "intent": "complaint_trend",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": [
            "şikayet geldi mi", "sikayet geldi mi", "şikayet var mı", "sikayet var mi",
            "klimalardan şikayet", "klimalardan sikayet", "hiç klimalardan",
            "bu hafta hiç", "bu hafta şikayet", "geçen hafta şikayet",
            "kaç şikayet", "kac sikayet", "şikayet trend",
        ],
        "patterns": [
            r"(?:bu\s+hafta|gecen\s+hafta|geçen\s+hafta).*(?:şikayet|sikayet)",
            r"(?:şikayet|sikayet)\s+geldi\s+m[ıi]",
            r"hi[cç]\s+.*(?:şikayet|sikayet)",
            r"(?:klima|su|wifi|temizlik|priz).*(?:şikayet|sikayet).*(?:geldi|var)\s*m",
            r"(?:şikayet|sikayet).*(?:geldi|var)\s*m[ıi].*(?:klima|su|wifi)",
            r"ka[cç]\s+(?:şikayet|sikayet)",
        ],
    },
    {
        "intent": "issue_status_followup",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": [
            "çözüldü mü", "cozuldu mu", "geçen haftaki", "gecen haftaki",
            "sorunu çözüldü", "sorunu cozuldu", "su sorunu çözüldü",
            "halledildi mi", "giderildi mi",
        ],
        "patterns": [
            r"(?:geçen\s+hafta|gecen\s+hafta|bu\s+hafta).*(?:çözüldü|cozuldu|halledildi|giderildi)",
            r"(?:su|klima|wifi|priz|temizlik).*(?:sorun|şikayet|sikayet).*(?:çözüldü|cozuldu)",
            r"(?:çözüldü|cozuldu|halledildi|giderildi)\s*m[uü]",
            r"geçen\s+haftaki\s+\w+\s+sorun",
            r"gecen\s+haftaki\s+\w+\s+sorun",
        ],
    },
    {
        "intent": "room_issue",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": ["oda sorun", "sorun var mı", "sorun var mi", "sorunlar kaldı", "açık sorun", "acik sorun"],
        "patterns": [
            r"oda\s+\d{3,4}.*(?:sorun|sikayet|sikayetler|kaldi|cozul|durum|acik|devam|rapor)",
            r"\d{3,4}\s*(?:nolu|te|no|de).*sorun",
            r"sorun\s+var\s+m[ıi]",
            r"hangi\s+sorunlar?\s+kald[ıi]",
        ],
    },
    {
        "intent": "cross_room_search",
        "department": "Engineering",
        "priority": "medium",
        "action_required": False,
        "keywords": ["hangi odalarda", "hangi odada", "sorunu olan oda", "sorun olan oda", "bozuk oda"],
        "patterns": [
            r"sorun[a-z]*\s+olan\s+oda",
            r"hangi\s*odal",
            r"(?:klima|wifi|priz|tv)\s*sorun[a-z]*\s+olan",
            r"\boda\s+var\s+m[iı]",
        ],
    },
    {
        "intent": "breakfast_menu",
        "department": "F&B",
        "priority": "low",
        "action_required": False,
        "keywords": [
            "kahvaltı de ne var", "kahvaltıda ne var", "kahvaltı menü", "kahvaltı neler",
            "kahvalti de ne var", "breakfast menu",
        ],
        "patterns": [r"kahvalt[iı].*(?:ne var|menü|menu|neler|içerik|icerik)"],
    },
    {
        "intent": "dirty_room",
        "department": "Housekeeping",
        "priority": "high",
        "action_required": True,
        "keywords": ["oda kirli", "oda çok kirli", "oda pis", "kirli oda", "oda lekeli", "oda cok kirli"],
        "patterns": [r"oda\s*(?:cok\s*)?(?:kirli|pis|lekeli|berbat)", r"(?:kirli|pis)\s*oda"],
    },
    {
        "intent": "check_in_time",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": ["check-in", "check in", "checkin", "giriş saati", "giris saati", "ne zaman girebilirim", "oda anahtarı"],
        "patterns": [r"check[\s-]?in", r"giri[sş]\s*saat"],
    },
    {
        "intent": "check_out_time",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": ["check-out", "check out", "checkout", "çıkış saati", "cikis saati", "geç çıkış", "gec cikis"],
        "patterns": [r"check[\s-]?out", r"ç[ıi]k[ıi][sş]\s*saat"],
    },
    {
        "intent": "pool_hours",
        "department": "Spa",
        "priority": "low",
        "action_required": False,
        "keywords": ["havuz saat", "havuz kaçta", "havuz ne zaman", "pool hours", "havuz kapan"],
        "patterns": [r"havuz\s*(?:saat|kaçta|ne zaman|kapan)"],
    },
    {
        "intent": "breakfast_hours",
        "department": "F&B",
        "priority": "low",
        "action_required": False,
        "keywords": ["kahvaltı saat", "kahvalti saat", "kahvaltı kaçta", "breakfast"],
        "patterns": [r"kahvalt[ıi]\s*(?:saat|kaçta|ne zaman)"],
    },
    {
        "intent": "spa_hours",
        "department": "Spa",
        "priority": "low",
        "action_required": False,
        "keywords": ["spa saat", "hamam saat", "masaj randevu"],
        "patterns": [r"spa\s*(?:saat|kaçta)"],
    },
    {
        "intent": "request_towel",
        "department": "Housekeeping",
        "priority": "medium",
        "action_required": True,
        "keywords": ["havlu istiyorum", "havlu lazım", "havlu gönder", "extra towel", "ek havlu", "havlu getir"],
        "patterns": [r"havlu\s*(?:istiyor|laz[ıi]m|g[öo]nder|getir|eksik)"],
    },
    {
        "intent": "request_cleaning",
        "department": "Housekeeping",
        "priority": "medium",
        "action_required": True,
        "keywords": ["oda temizliği", "temizlik istiyorum", "oda temizlensin", "housekeeping"],
        "patterns": [r"(?:oda\s*)?temizlik", r"temizlen(?:sin|medi)"],
    },
    {
        "intent": "wifi_issue",
        "department": "Engineering",
        "priority": "high",
        "action_required": True,
        "keywords": ["wifi çalışmıyor", "wifi yok", "internet yok", "internet gelmiyor", "wi-fi sorun", "ağ yok"],
        "patterns": [r"wi[\s-]?fi", r"internet\s*(?:yok|gelmiyor|çalışm|calism|kesik|kop)"],
    },
    {
        "intent": "ac_issue",
        "department": "Engineering",
        "priority": "high",
        "action_required": True,
        "keywords": ["klima çalışmıyor", "klima bozuk", "klima arız", "soğutmuyor", "sogutmuyor", "ısıtmıyor"],
        "patterns": [r"klima\s*(?:çalışm|calism|bozuk|arız|ariz|soğutm|sogutm|ısıtm|isitm)"],
    },
    {
        "intent": "tv_issue",
        "department": "Engineering",
        "priority": "medium",
        "action_required": True,
        "keywords": ["tv çalışmıyor", "televizyon bozuk", "kumanda"],
        "patterns": [r"(?:tv|televizyon)\s*(?:çalışm|calism|bozuk|açılm)"],
    },
    {
        "intent": "plumbing_issue",
        "department": "Engineering",
        "priority": "high",
        "action_required": True,
        "keywords": ["su basıncı", "tuvalet", "lavabo tık", "duş", "dus", "su kaç"],
        "patterns": [r"(?:su\s*bas[ıi]nc|tuvalet|lavabo|du[sş])\s*(?:düş|dus|t[ıi]k|kaç|yok)"],
    },
    {
        "intent": "invoice_request",
        "department": "Finance",
        "priority": "medium",
        "action_required": True,
        "keywords": ["fatura istiyorum", "fatura talep", "e-fatura", "fatura gönder"],
        "patterns": [r"fatura\s*(?:istiyor|talep|laz[ıi]m|g[öo]nder)"],
    },
    {
        "intent": "deposit_query",
        "department": "Finance",
        "priority": "low",
        "action_required": False,
        "keywords": ["depozito", "depozit", "güvence bedeli", "iade"],
        "patterns": [r"depozit"],
    },
    {
        "intent": "lost_item",
        "department": "Security",
        "priority": "medium",
        "action_required": True,
        "keywords": ["kaybettim", "kayıp eşya", "kayip esya", "unuttum", "lost and found", "bulunamadı"],
        "patterns": [r"kay[ıi]p\s*(?:e[sş]ya|şey)", r"(?:unuttum|kaybettim)"],
    },
    {
        "intent": "complaint",
        "department": "Front Office",
        "priority": "high",
        "action_required": True,
        "keywords": ["şikayet", "sikayet", "memnun değilim", "berbat", "rezalet", "kabul edilemez"],
        "patterns": [r"şik[ae]yet", r"sikayet", r"memnun\s*de[ğg]il"],
    },
    {
        "intent": "compliment",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": ["teşekkür", "tesekkur", "harika", "mükemmel", "muhteşem", "beğendim"],
        "patterns": [r"te[sş]ekk[üu]r", r"(?:harika|m[üu]kemmel|be[ğg]endim)"],
    },
    {
        "intent": "reservation",
        "department": "Front Office",
        "priority": "medium",
        "action_required": True,
        "keywords": ["rezervasyon", "oda ayırt", "booking", "müsaitlik", "musaitlik"],
        "patterns": [r"rezervasyon", r"(?:oda|masa)\s*(?:ayırt|ayirt|rezerv)"],
    },
    {
        "intent": "transfer_request",
        "department": "Concierge",
        "priority": "medium",
        "action_required": True,
        "keywords": ["havalimanı transfer", "airport transfer", "transfer istiyorum", "shuttle"],
        "patterns": [r"(?:havaliman[ıi]|airport)\s*transfer", r"transfer\s*(?:istiyor|talep|laz[ıi]m)"],
    },
    {
        "intent": "vegan_options",
        "department": "F&B",
        "priority": "low",
        "action_required": False,
        "keywords": ["vegan", "vejetaryen", "vegetarian", "glutensiz", "gluten free", "alerjen"],
        "patterns": [r"vegan|vejetaryen|glutensiz|gluten\s*free"],
    },
    {
        "intent": "parking_query",
        "department": "Front Office",
        "priority": "low",
        "action_required": False,
        "keywords": ["otopark", "parking", "park yeri", "araç park"],
        "patterns": [r"otopark|parking|park\s*yeri"],
    },
    {
        "intent": "room_service",
        "department": "F&B",
        "priority": "medium",
        "action_required": True,
        "keywords": ["oda servisi", "room service", "yemek sipariş"],
        "patterns": [r"oda\s*servis", r"room\s*service"],
    },
    {
        "intent": "noise_complaint",
        "department": "Security",
        "priority": "high",
        "action_required": True,
        "keywords": ["gürültü", "gurultu", "ses var", "uyuyamıyorum", "çok gürültülü"],
        "patterns": [r"g[üu]r[üu]lt[üu]", r"uyuyam[ıi]yorum"],
    },
    {
        "intent": "early_checkin",
        "department": "Front Office",
        "priority": "medium",
        "action_required": False,
        "keywords": ["erken giriş", "erken check-in", "early checkin"],
        "patterns": [r"erken\s*(?:giri[sş]|check)"],
    },
]

_DEPT_ALIASES = {
    "Front Office": "resepsiyon",
    "Housekeeping": "housekeeping",
    "F&B": "restaurant",
    "Spa": "spa",
    "Engineering": "teknik",
    "Security": "guvenlik",
    "Finance": "muhasebe",
    "Sales": "satis",
    "Concierge": "turizm",
}


class IntentService:
    """Intent detection and department routing."""

    @classmethod
    def list_intents(cls) -> list[dict[str, Any]]:
        return [
            {
                "intent": r["intent"],
                "department": r["department"],
                "priority": r["priority"],
                "action_required": r["action_required"],
            }
            for r in _INTENT_RULES
        ]

    @classmethod
    def detect(cls, query: str, history: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        norm = normalize_turkish(query.lower())
        entities: dict[str, str] = {}
        history = history or []

        room_m = (
            re.search(r"\boda\s+(\d{3,4})\b", norm)
            or re.search(r"\b(\d{3,4})\s*(?:nolu|te)\b", norm)
            or re.search(r"\b(\d{3,4})\s+de\b", norm)
        )
        if room_m:
            entities["room_number"] = room_m.group(1)

        best: Optional[dict[str, Any]] = None
        best_score = 0.0

        # Analitik / takip soruları — misafir şikayet kaydı değil
        is_status_followup = bool(
            re.search(r"(?:çözüldü|cozuldu|halledildi|giderildi)\s*m", norm)
            or re.search(
                r"(?:geçen\s+haftaki|gecen\s+haftaki|geçen\s+hafta|gecen\s+hafta).*(?:sorun|şikayet|sikayet).*(?:çözüldü|cozuldu|halledildi|giderildi)",
                norm,
            )
        )
        is_trend_query = bool(
            not is_status_followup
            and (
                re.search(r"(?:şikayet|sikayet)\s+(?:geldi|var)\s*m", norm)
                or re.search(r"hi[cç]\s+.*(?:şikayet|sikayet)", norm)
                or (
                    any(t in norm for t in ("bu hafta", "gecen hafta", "geçen hafta"))
                    and any(t in norm for t in ("şikayet", "sikayet"))
                )
            )
        )
        is_own_room_report = bool(
            re.search(r"odamda\s+(?:bir\s+)?(?:sorun|problem|ar[ıi]za)", norm)
        )
        is_meal_today = bool(
            ("yemekte" in norm or re.search(r"(?:[öo]ğ?le|ak[sş]am)\s+yeme", norm))
            and "kahvalt" not in norm
        )

        for rule in _INTENT_RULES:
            score = 0.0
            intent_id = rule["intent"]
            for kw in rule.get("keywords", []):
                kw_n = normalize_turkish(kw.lower())
                if kw_n in norm:
                    score += 2.0 if " " in kw_n else 1.0
            for pat in rule.get("patterns", []):
                if re.search(pat, norm, re.IGNORECASE | re.UNICODE):
                    score += 2.5

            # Operasyonel öncelik boost
            if intent_id == "issue_status_followup" and is_status_followup:
                score += 5.0
            if intent_id == "complaint_trend" and is_trend_query:
                score += 4.0
            if intent_id == "meal_menu_today" and is_meal_today:
                score += 4.0
            if intent_id == "room_issue_report" and is_own_room_report:
                score += 3.5

            # Yanlış yönlendirmeyi engelle
            if intent_id == "complaint" and (is_trend_query or is_status_followup):
                score *= 0.05
            if intent_id == "complaint_trend" and is_status_followup:
                score *= 0.1
            if intent_id == "breakfast_menu" and is_meal_today and "kahvalt" not in norm:
                score *= 0.05
            if intent_id in ("room_issue", "cross_room_search") and is_own_room_report:
                score *= 0.15
            if intent_id in ("ac_issue", "wifi_issue", "plumbing_issue") and (is_trend_query or is_status_followup):
                score *= 0.2
            if intent_id == "clarification":
                score = 0.0

            if score > best_score:
                best_score = score
                best = rule

        if not best or best_score < 1.0:
            # Bağlamsal "neler var" — önceki turda yemek/vegan konusu varsa
            if norm in ("neler var", "ne var") and history:
                combined = " ".join(
                    m.get("content", "")
                    for m in history
                    if m.get("role") == "user"
                )
                combined_norm = normalize_turkish(combined.lower())
                if any(k in combined_norm for k in ("vegan", "vejetaryen", "kahvalti", "kahvaltı", "yemek", "restoran")):
                    return {
                        "intent": "contextual_neler_var",
                        "department": "F&B",
                        "priority": "low",
                        "action_required": False,
                        "entities": entities,
                        "confidence": 0.75,
                        "department_key": "restaurant",
                    }
            return {
                "intent": "general_inquiry",
                "department": "Front Office",
                "priority": "low",
                "action_required": False,
                "entities": entities,
                "confidence": 0.3,
            }

        return {
            "intent": best["intent"],
            "department": best["department"],
            "priority": best["priority"],
            "action_required": best["action_required"],
            "entities": entities,
            "confidence": min(1.0, best_score / 5.0),
            "department_key": _DEPT_ALIASES.get(best["department"], "resepsiyon"),
        }
