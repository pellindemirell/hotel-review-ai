"""
Entity bazlı operasyonel sorun takibi — oda, havuz, mobil uygulama, kargo vb.
RoomIssueService ile geriye dönük uyumluluk korunur.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.entity_tracker_store import (
    EntityComment,
    EntityIssue,
    EntityTrackerStore,
    get_entity_tracker_store,
)
from app.services.ontology_service import OntologyService
from app.services.turkish_nlp_utils import normalize_turkish

# Oda numarası kalıpları (geriye dönük)
_ROOM_PATTERNS = [
    re.compile(r"\boda\s+(\d{3,4})\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(\d{3,4})\s*nolu\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(\d{3,4})\s*numaralı\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(\d{3,4})\s*numara(?:lı|da|da)?\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(\d{3,4})\s*['']?te\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(\d{3,4})\s*no\b", re.IGNORECASE | re.UNICODE),
]

ISSUE_TYPES: dict[str, list[str]] = {
    "klima": ["klima", "klimalar", "klimalardan", "soğutma", "ısıtma", "kliması", "klimasi"],
    "priz": ["priz", "elektrik", "prizler"],
    "wifi": ["wifi", "internet", "wi-fi", "ağ", "ag", "kopuyor", "kopma"],
    "tv": ["tv", "televizyon", "kumanda"],
    "su": ["su sorunu", "su arıza", "su kaç", "su basınc", "su yok", "su problemi", "su şikayet"],
    "banyo": ["banyo", "tuvalet", "lavabo", "klozet"],
    "havlu": ["havlu", "havlular", "çarşaf", "carsaf", "yatak"],
    "asansör": ["asansör", "asansor", "lift"],
    "lamba": ["lamba", "ampul", "aydınlatma", "isik", "ışık"],
    "duş": ["duş", "dus", "sıcak su", "sicak su"],
    "minibar": ["minibar", "buzdolabı", "buzdolabi"],
    "kapı": ["kapı", "kapi", "kilit"],
    "temizlik": ["temizlik", "kirli", "pis", "toz", "leke"],
    "gürültü": ["gürültü", "gurultu", "ses", "inşaat"],
    "yavaşlık": ["yavaş", "yavas", "gecikme", "donma", "takılma"],
    "teslimat": ["teslimat", "gecikme", "gec geldi", "ulasimadi"],
    "lezzet": ["lezzet", "tuzlu", "bayat", "soğuk yemek"],
    "boyut": ["küçük", "kucuk", "dar", "alan"],
    "personel": ["kaba", "ilgisiz", "yardımcı", "yardimci", "temsilci"],
    "atm": ["atm", "bankamatik", "nakit"],
}

RESOLUTION_KEYWORDS = (
    "düzeldi", "duzeldi", "giderildi", "tamir edildi", "çözüldü", "cozuldu",
    "halledildi", "yapıldı", "yapildi", "onarıldı", "onarildi",
    "çalışıyor artık", "sorun giderildi", "tamamlandı", "tamamlandi",
    "düzeltildi", "duzeltildi", "teslim edildi", "geldi",
)

SCHEDULE_KEYWORDS = (
    "teknik servis gelecek", "servis gelecek", "randevu", "planlandı",
    "planlandi", "yarına", "yarina", "gelecek hafta",
)

_DATE_PATTERN = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")

_CROSS_ROOM_PATTERNS = [
    re.compile(r"klima\s+sorunu\s+olan\s+oda", re.IGNORECASE | re.UNICODE),
    re.compile(r"sorun[a-z]*\s+olan\s+oda", re.IGNORECASE | re.UNICODE),
    re.compile(r"hangi\s+odalarda", re.IGNORECASE | re.UNICODE),
    re.compile(r"(?:klima|wifi|tv|priz|su)\s+sorunu\s+olan", re.IGNORECASE | re.UNICODE),
    re.compile(r"sorunlu\s+oda", re.IGNORECASE | re.UNICODE),
    re.compile(r"odalarda.*(?:proble|sorun)", re.IGNORECASE | re.UNICODE),
    re.compile(r"hangi\s*odalarda.*(?:sorun|proble)", re.IGNORECASE | re.UNICODE),
]

_COMPLAINT_TREND_PATTERNS = [
    re.compile(r"(?:şikayet|sikayet)\s+geldi\s+m", re.IGNORECASE | re.UNICODE),
    re.compile(r"hi[cç]\s+.*(?:şikayet|sikayet)", re.IGNORECASE | re.UNICODE),
    re.compile(r"(?:bu\s+hafta|gecen\s+hafta|geçen\s+hafta).*(?:şikayet|sikayet|sorun)", re.IGNORECASE | re.UNICODE),
    re.compile(r"(?:klima|su|wifi|priz|temizlik).*(?:şikayet|sikayet)", re.IGNORECASE | re.UNICODE),
]

_STATUS_FOLLOWUP_PATTERNS = [
    re.compile(r"(?:çözüldü|cozuldu|halledildi|giderildi)\s*m", re.IGNORECASE | re.UNICODE),
    re.compile(
        r"(?:geçen\s+haftaki|gecen\s+haftaki)\s+\w+\s+(?:sorun|şikayet|sikayet|ar[ıi]za)",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"(?:geçen\s+hafta|gecen\s+hafta|bu\s+hafta).*(?:sorun|şikayet|sikayet).*(?:çözül|cozul|halledil|gideril)",
        re.IGNORECASE | re.UNICODE,
    ),
]

_ROOM_HISTORY_PATTERNS = [
    re.compile(r"daha\s+once.*sorun", re.IGNORECASE | re.UNICODE),
    re.compile(r"daha\s+önce.*sorun", re.IGNORECASE | re.UNICODE),
    re.compile(r"gecmis.*sorun", re.IGNORECASE | re.UNICODE),
    re.compile(r"geçmiş.*sorun", re.IGNORECASE | re.UNICODE),
]

_ENTITY_QUERY_MARKERS = (
    "sorun", "sikayet", "en son", "son sorun", "kaldi", "cozuldu",
    "giderildi", "durum", "rapor", "gecmis", "acik", "devam",
    "gecikme", "memnuniyet", "sikayetler", "ne oldu", "hangi",
    "var mi", "var mı",
)


class EntityTrackerService:
    """Her türlü entity için sorun çıkarımı, takibi ve chatbot cevabı."""

    def __init__(self, store: Optional[EntityTrackerStore] = None) -> None:
        self.store = store or get_entity_tracker_store()

    @staticmethod
    def extract_room_number(text: str) -> Optional[str]:
        normalized = normalize_turkish(text.lower())
        for pattern in _ROOM_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return match.group(1)
        return None

    @classmethod
    def extract_entity(cls, text: str) -> Optional[dict[str, Any]]:
        """Metinden entity bilgisi çıkarır."""
        entities = OntologyService.search_entity(text)
        if entities:
            return entities[0]
        room = cls.extract_room_number(text)
        if room:
            return {
                "entity_id": f"room_{room}",
                "entity_key": room,
                "entity_label": f"Oda {room}",
                "entity_type": "room",
                "domain": "turizm",
                "subdomain": "otel",
                "department": "housekeeping",
            }
        return None

    @staticmethod
    def extract_issue_type(text: str) -> Optional[str]:
        normalized = normalize_turkish(text.lower())
        # "su" tek başına çok genel; yalnızca bağlamlı eşleşsin
        best_type: Optional[str] = None
        best_pos = len(normalized) + 1
        best_len = 0
        for issue_type, keywords in ISSUE_TYPES.items():
            for kw in keywords:
                kw_n = normalize_turkish(kw)
                pos = normalized.find(kw_n)
                if pos < 0:
                    continue
                # Daha uzun / daha spesifik anahtar kelimeyi tercih et
                if pos < best_pos or (pos == best_pos and len(kw_n) > best_len):
                    best_type = issue_type
                    best_pos = pos
                    best_len = len(kw_n)
        # Düz "su" kelimesi (su sorunu / su arızası vb.)
        if best_type is None and re.search(r"\bsu\b", normalized):
            if any(k in normalized for k in ("sorun", "ariza", "arıza", "sikayet", "şikayet", "kac", "kaç", "basinc", "basınç", "yok", "problem")):
                return "su"
        return best_type

    @classmethod
    def parse_time_window(cls, query: str) -> tuple[Optional[datetime], Optional[datetime], str]:
        """Sorudan zaman penceresi çıkarır. (start, end, label)"""
        norm = normalize_turkish(query.lower())
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today_start.weekday()  # Mon=0
        this_week_start = today_start - timedelta(days=weekday)
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start

        if "gecen hafta" in norm or "geçen hafta" in norm or "gecen haftaki" in norm or "geçen haftaki" in norm:
            return last_week_start, last_week_end, "geçen hafta"
        if "bu hafta" in norm:
            return this_week_start, now + timedelta(days=1), "bu hafta"
        if "bugun" in norm or "bugün" in norm:
            return today_start, now + timedelta(days=1), "bugün"
        return None, None, ""

    @classmethod
    def is_issue_status_followup_query(cls, query: str) -> bool:
        norm = normalize_turkish(query.lower())
        if re.search(r"(?:çözüldü|cozuldu|halledildi|giderildi)\s*m", norm):
            return True
        return any(p.search(norm) for p in _STATUS_FOLLOWUP_PATTERNS)

    @classmethod
    def is_complaint_trend_query(cls, query: str) -> bool:
        norm = normalize_turkish(query.lower())
        # Durum takibi ("çözüldü mü") trend değildir
        if cls.is_issue_status_followup_query(query):
            return False
        if any(p.search(norm) for p in _COMPLAINT_TREND_PATTERNS):
            return True
        if re.search(r"(?:şikayet|sikayet)\s+(?:geldi|var)\s*m", norm):
            return True
        return False

    @staticmethod
    def is_resolution_comment(text: str) -> bool:
        normalized = normalize_turkish(text.lower())
        return any(kw in normalized for kw in RESOLUTION_KEYWORDS)

    @staticmethod
    def is_scheduled_comment(text: str) -> bool:
        normalized = normalize_turkish(text.lower())
        return any(kw in normalized for kw in SCHEDULE_KEYWORDS)

    @staticmethod
    def extract_scheduled_date(text: str) -> Optional[str]:
        match = _DATE_PATTERN.search(text)
        if not match:
            return None
        day, month, year = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            return dt.date().isoformat()
        except ValueError:
            return None

    @classmethod
    def is_entity_query(cls, query: str) -> bool:
        if cls.is_cross_room_query(query):
            return False
        normalized = normalize_turkish(query.lower())
        entity = cls.extract_entity(query)
        if not entity:
            return False
        has_marker = any(m in normalized for m in _ENTITY_QUERY_MARKERS)
        has_room = entity.get("entity_type") == "room"
        return bool(has_marker or has_room)

    @classmethod
    def is_cross_room_query(cls, query: str) -> bool:
        norm = normalize_turkish(query.lower())
        if any(p.search(norm) for p in _CROSS_ROOM_PATTERNS):
            return True
        if re.search(r"hangi\s+oda", norm) and "sorun" in norm:
            return True
        if "sorun" in norm and re.search(r"\boda\s+var\s+m[ıi]", norm):
            return True
        if "odalarda" in norm and any(k in norm for k in ("sorun", "proble", "problem")):
            return True
        # Konu bazlı şikayet trendi → çapraz oda / analytics
        if cls.is_complaint_trend_query(query) and cls.extract_issue_type(query):
            return True
        return False

    @classmethod
    def is_room_history_query(cls, query: str) -> bool:
        norm = normalize_turkish(query.lower())
        if not any(p.search(norm) for p in _ROOM_HISTORY_PATTERNS):
            return False
        return bool(cls.extract_room_number(query) or re.search(r"\boda\s+\d{3,4}\b", norm))

    @classmethod
    def is_bare_room_number(cls, query: str) -> bool:
        stripped = (query or "").strip()
        return bool(re.fullmatch(r"\d{2,4}", stripped))

    @classmethod
    def is_food_context_query(cls, query: str) -> bool:
        norm = normalize_turkish(query.lower())
        food_markers = (
            "kahvalti", "kahvaltı", "yemek", "restoran", "menu", "menü", "bufe",
            "büfe", "icecek", "içecek", "bar", "pastane", "dondurma",
        )
        return any(m in norm for m in food_markers)

    @staticmethod
    def is_room_query(query: str) -> bool:
        """Geriye dönük uyumluluk."""
        normalized = normalize_turkish(query.lower())
        room_num = EntityTrackerService.extract_room_number(query)
        return bool(room_num and ("oda" in normalized or any(m in normalized for m in _ENTITY_QUERY_MARKERS)))

    @staticmethod
    def _parse_dt(value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_date_tr(iso_value: str) -> str:
        dt = EntityTrackerService._parse_dt(iso_value)
        if not dt:
            return iso_value[:10] if len(iso_value) >= 10 else iso_value
        return dt.strftime("%d.%m.%Y")

    def register_from_comment(
        self,
        comment: str,
        review_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[EntityIssue]:
        entity = self.extract_entity(comment)
        if not entity:
            return None

        issue_type = self.extract_issue_type(comment)
        ts = created_at or datetime.now(timezone.utc).isoformat()
        comment_id = str(uuid.uuid4())[:8]
        room_number = entity.get("entity_key") if entity.get("entity_type") == "room" else None

        self.store.add_comment(
            EntityComment(
                id=comment_id,
                entity_id=entity["entity_id"],
                entity_type=entity.get("entity_type", "facility"),
                entity_label=entity.get("entity_label", entity["entity_id"]),
                comment=comment,
                issue_type=issue_type,
                review_id=review_id,
                created_at=ts,
                is_resolution=self.is_resolution_comment(comment),
                domain=entity.get("domain", ""),
                department=entity.get("department", ""),
                room_number=room_number,
            )
        )

        if not issue_type:
            return None

        if self.is_resolution_comment(comment):
            existing = self.store.find_open_issue(entity["entity_id"], issue_type)
            if existing:
                existing.status = "resolved"
                existing.resolved_at = ts
                existing.last_reported = ts
                existing.comment_ids.append(comment_id)
                return self.store.update_issue(existing)
            return None

        existing = self.store.find_open_issue(entity["entity_id"], issue_type)
        if existing:
            existing.last_reported = ts
            existing.comment_ids.append(comment_id)
            if self.is_scheduled_comment(comment):
                existing.status = "scheduled"
                sched = self.extract_scheduled_date(comment)
                if sched:
                    existing.scheduled_date = sched
            return self.store.update_issue(existing)

        status = "scheduled" if self.is_scheduled_comment(comment) else "open"
        scheduled_date = self.extract_scheduled_date(comment) if status == "scheduled" else None

        issue = EntityIssue(
            id=str(uuid.uuid4())[:8],
            entity_id=entity["entity_id"],
            entity_type=entity.get("entity_type", "facility"),
            entity_label=entity.get("entity_label", entity["entity_id"]),
            issue_type=issue_type,
            status=status,
            domain=entity.get("domain", ""),
            department=entity.get("department", ""),
            first_reported=ts,
            last_reported=ts,
            scheduled_date=scheduled_date,
            comment_ids=[comment_id],
            notes=comment[:120],
            room_number=room_number,
        )
        return self.store.add_issue(issue)

    def get_entity_report(self, entity_id: str) -> dict[str, Any]:
        issues = [i for i in self.store.all_issues() if i.entity_id == entity_id]
        comments = [c for c in self.store.all_comments() if c.entity_id == entity_id]
        issues.sort(key=lambda x: x.first_reported)
        comments.sort(key=lambda x: x.created_at)

        label = issues[0].entity_label if issues else (
            comments[0].entity_label if comments else entity_id
        )
        entity_type = issues[0].entity_type if issues else (
            comments[0].entity_type if comments else "unknown"
        )
        room_number = issues[0].room_number if issues else (
            comments[0].room_number if comments else None
        )

        return {
            "entity_id": entity_id,
            "entity_label": label,
            "entity_type": entity_type,
            "room_number": room_number,
            "issues": [i.to_dict() for i in issues],
            "comments": [c.to_dict() for c in comments],
            "open_count": sum(1 for i in issues if i.status in ("open", "scheduled")),
            "resolved_count": sum(1 for i in issues if i.status == "resolved"),
        }

    def get_room_report(self, room_number: str) -> dict[str, Any]:
        """Geriye dönük uyumluluk."""
        report = self.get_entity_report(f"room_{room_number}")
        report["room_number"] = room_number
        return report

    def get_open_issues(self, entity_id: str) -> list[EntityIssue]:
        return [
            i for i in self.store.all_issues()
            if i.entity_id == entity_id and i.status in ("open", "scheduled")
        ]

    def get_resolved_issues(self, entity_id: str) -> list[EntityIssue]:
        return [
            i for i in self.store.all_issues()
            if i.entity_id == entity_id and i.status == "resolved"
        ]

    def find_cross_entity_patterns(self, issue_type: str, days: int = 7) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        entities: dict[str, EntityIssue] = {}
        for issue in self.store.all_issues():
            if issue.issue_type != issue_type:
                continue
            if issue.status not in ("open", "scheduled"):
                continue
            dt = self._parse_dt(issue.last_reported)
            if dt and dt < cutoff:
                continue
            entities[issue.entity_id] = issue
        if len(entities) < 2:
            return []
        return [
            {
                "entity_id": eid,
                "entity_label": issue.entity_label,
                "entity_type": issue.entity_type,
                "issue_type": issue_type,
                "status": issue.status,
                "last_reported": issue.last_reported,
            }
            for eid, issue in sorted(entities.items())
        ]

    def find_cross_room_patterns(self, issue_type: str, days: int = 7) -> list[dict[str, Any]]:
        patterns = self.find_cross_entity_patterns(issue_type, days)
        return [
            {
                "room_number": p["entity_id"].replace("room_", ""),
                "issue_type": p["issue_type"],
                "status": p["status"],
                "last_reported": p["last_reported"],
            }
            for p in patterns
            if p.get("entity_type") == "room"
        ]

    def find_rooms_with_open_issue(self, issue_type: str, days: int = 30) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results: list[dict[str, Any]] = []
        for issue in self.store.all_issues():
            if issue.issue_type != issue_type:
                continue
            if issue.status not in ("open", "scheduled"):
                continue
            if issue.entity_type != "room":
                continue
            dt = self._parse_dt(issue.last_reported)
            if dt and dt < cutoff:
                continue
            results.append({
                "entity_id": issue.entity_id,
                "entity_label": issue.entity_label,
                "entity_type": issue.entity_type,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "last_reported": issue.last_reported,
                "room_number": issue.room_number,
            })
        return sorted(results, key=lambda x: x["last_reported"])

    def search_issues_by_type_and_time(
        self,
        issue_type: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        statuses: Optional[tuple[str, ...]] = None,
        rooms_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Zaman ve tür filtreli sorun araması (açık + çözülen)."""
        results: list[dict[str, Any]] = []
        for issue in self.store.all_issues():
            if issue_type and issue.issue_type != issue_type:
                continue
            if statuses and issue.status not in statuses:
                continue
            if rooms_only and issue.entity_type != "room":
                continue
            # Zaman: first_reported veya last_reported pencereye düşsün
            dt_first = self._parse_dt(issue.first_reported)
            dt_last = self._parse_dt(issue.last_reported)
            dt_resolved = self._parse_dt(issue.resolved_at) if issue.resolved_at else None
            in_window = False
            for dt in (dt_first, dt_last, dt_resolved):
                if not dt:
                    continue
                if start and dt < start:
                    continue
                if end and dt >= end:
                    continue
                in_window = True
                break
            if start or end:
                if not in_window:
                    continue
            results.append({
                "entity_id": issue.entity_id,
                "entity_label": issue.entity_label,
                "entity_type": issue.entity_type,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "first_reported": issue.first_reported,
                "last_reported": issue.last_reported,
                "resolved_at": issue.resolved_at,
                "room_number": issue.room_number,
            })
        return sorted(results, key=lambda x: x["last_reported"], reverse=True)

    def format_complaint_trend_answer(self, query: str) -> Optional[str]:
        """'Bu hafta klimalardan şikayet geldi mi?' — analitik/tracker cevabı."""
        if not self.is_complaint_trend_query(query) and not self.extract_issue_type(query):
            return None

        issue_type = self.extract_issue_type(query)
        start, end, label = self.parse_time_window(query)
        if not start:
            # Varsayılan: bu hafta
            start, end, label = self.parse_time_window("bu hafta")

        days = max(1, (datetime.now(timezone.utc) - start).days + 1) if start else 7

        if issue_type:
            # Önce açık odaları göster (kullanıcı beklentisi: 504, 702, 705)
            open_rooms = self.find_rooms_with_open_issue(issue_type, days=max(days, 14))
            window_hits = self.search_issues_by_type_and_time(
                issue_type=issue_type, start=start, end=end, rooms_only=True,
            )
            if not open_rooms and not window_hits:
                return (
                    f"{label.capitalize()} için kayıtlı **{issue_type}** şikayeti bulunmuyor.\n\n"
                    "Yeni bildirimler geldiğinde otomatik takip edilir."
                )

            open_n = len(open_rooms)
            closed_n = sum(1 for h in window_hits if h["status"] == "resolved")
            room_labels = []
            shown: set[str] = set()
            for room in open_rooms:
                key = room["entity_id"]
                if key in shown:
                    continue
                shown.add(key)
                room_labels.append(room.get("room_number") or room["entity_label"].replace("Oda ", ""))

            lines = [
                f"{label.capitalize()} **{issue_type}** şikayeti: "
                f"{open_n} açık, {closed_n} kapalı."
                + (f" Odalar: {', '.join(room_labels)}." if room_labels else ""),
                "",
            ]
            for room in open_rooms:
                status_tr = "planlandı" if room["status"] == "scheduled" else "açık"
                last = self._format_date_tr(room["last_reported"])
                lines.append(f"- **{room['entity_label']}**: {status_tr} (son: {last})")
            for hit in window_hits:
                if hit["entity_id"] in shown:
                    continue
                if hit["status"] == "resolved":
                    shown.add(hit["entity_id"])
                    resolved = self._format_date_tr(hit.get("resolved_at") or hit["last_reported"])
                    lines.append(f"- **{hit['entity_label']}**: çözüldü ({resolved})")
            if len(shown) == 0:
                lines.append("Bu dönemde eşleşen kayıt yok.")
            return "\n".join(lines).strip()

        # Tür yok — genel açık sorun özeti
        return self.format_all_open_issues_summary(days=days)

    def format_issue_status_followup_answer(self, query: str) -> Optional[str]:
        """'Geçen haftaki su sorunu çözüldü mü?' — tracker geçmişi."""
        if not self.is_issue_status_followup_query(query) and "cozuldu" not in normalize_turkish(query.lower()):
            # Yine de çözüldü mü kalıbı varsa devam
            if not re.search(r"(?:çözüldü|cozuldu)\s*m", normalize_turkish(query.lower())):
                return None

        issue_type = self.extract_issue_type(query)
        start, end, label = self.parse_time_window(query)
        if not start:
            # "geçen haftaki" yoksa son 14 gün
            end = datetime.now(timezone.utc) + timedelta(days=1)
            start = end - timedelta(days=14)
            label = "son dönem"

        hits = self.search_issues_by_type_and_time(
            issue_type=issue_type,
            start=start,
            end=end,
            rooms_only=False,
        )
        # Tür bulunamadıysa anahtar kelime ile geniş ara
        if not hits and issue_type is None:
            norm = normalize_turkish(query.lower())
            for itype in ("su", "klima", "wifi", "priz", "temizlik", "duş"):
                if itype in norm or (itype == "su" and re.search(r"\bsu\b", norm)):
                    hits = self.search_issues_by_type_and_time(
                        issue_type=itype, start=start, end=end,
                    )
                    issue_type = itype
                    break

        topic = issue_type or "ilgili"
        if not hits:
            return (
                f"{label.capitalize()} için kayıtlı **{topic}** sorunu bulunamadı.\n\n"
                "Belirli bir oda biliyorsanız oda numarasını yazabilirsiniz "
                "(ör. 'oda 504 de su sorunu çözüldü mü?')."
            )

        resolved = [h for h in hits if h["status"] == "resolved"]
        open_ones = [h for h in hits if h["status"] in ("open", "scheduled")]

        lines = [f"**{label.capitalize()} — {topic} sorunu durumu:**", ""]
        if resolved:
            lines.append("Çözülen kayıtlar:")
            for h in resolved:
                when = self._format_date_tr(h.get("resolved_at") or h["last_reported"])
                lines.append(f"- **{h['entity_label']}**: evet, {when} tarihinde giderildi")
            lines.append("")
        if open_ones:
            lines.append("Hâlâ açık / devam eden:")
            for h in open_ones:
                status_tr = "planlandı" if h["status"] == "scheduled" else "açık"
                lines.append(f"- **{h['entity_label']}**: {status_tr}")
            lines.append("")

        if resolved and not open_ones:
            lines.append(f"Özet: Evet — {label} {topic} sorunu çözülmüş görünüyor.")
        elif open_ones and not resolved:
            lines.append(f"Özet: Hayır — {topic} sorunu hâlâ açık kayıtlı.")
        elif resolved and open_ones:
            lines.append("Özet: Bir kısmı çözüldü, bir kısmı hâlâ açık.")

        return "\n".join(lines).strip()

    def find_all_rooms_with_open_issues(self, days: int = 30) -> list[dict[str, Any]]:
        """Tüm açık oda sorunlarını döner."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results: list[dict[str, Any]] = []
        for issue in self.store.all_issues():
            if issue.status not in ("open", "scheduled"):
                continue
            if issue.entity_type != "room":
                continue
            dt = self._parse_dt(issue.last_reported)
            if dt and dt < cutoff:
                continue
            results.append({
                "entity_id": issue.entity_id,
                "entity_label": issue.entity_label,
                "entity_type": issue.entity_type,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "last_reported": issue.last_reported,
                "room_number": issue.room_number,
            })
        return sorted(results, key=lambda x: x["last_reported"])

    def format_all_open_issues_summary(self, days: int = 30) -> str:
        """Odalar genelinde açık sorun özeti."""
        rooms = self.find_all_rooms_with_open_issues(days=days)
        if not rooms:
            return (
                "🏨 **Açık oda sorunu kaydı bulunmuyor.**\n\n"
                "Son 30 günde takip edilen açık oda sorunu yok. "
                "Yeni şikayetler analiz edildiğinde otomatik takip edilir."
            )
        by_type: dict[str, list[dict[str, Any]]] = {}
        for room in rooms:
            by_type.setdefault(room["issue_type"], []).append(room)

        lines = ["🏨 **Açık sorunlu odalar (son 30 gün):**", ""]
        for itype, entries in sorted(by_type.items()):
            labels = []
            for e in entries:
                label = e.get("entity_label") or f"Oda {e.get('room_number', '?')}"
                status_tr = "planlandı" if e["status"] == "scheduled" else "açık"
                labels.append(f"{label} ({status_tr})")
            lines.append(f"- **{itype.title()}**: {', '.join(labels)}")
        return "\n".join(lines).strip()

    def format_recent_issues_summary(self, limit: int = 8) -> str:
        """Oda belirtilmemiş geçmiş soru için son kayıtlar."""
        issues = sorted(
            [i for i in self.store.all_issues() if i.entity_type == "room"],
            key=lambda x: x.last_reported,
            reverse=True,
        )[:limit]
        if not issues:
            return (
                "Son dönemde kayıtlı oda sorunu bulunmuyor. "
                "Belirli bir oda için 'oda XXX de daha önce sorun olmuş mu?' diye sorabilirsiniz."
            )
        lines = ["**Son oda sorun kayıtları:**", ""]
        for issue in issues:
            last = self._format_date_tr(issue.last_reported)
            status_tr = issue.status
            lines.append(
                f"- {issue.entity_label}: {issue.issue_type} ({status_tr}, son: {last})"
            )
        lines.append("")
        lines.append("Belirli bir oda için oda numarasını yazın (ör. 'oda 504 de sorun var mı?').")
        return "\n".join(lines)

    def format_cross_room_chat_answer(self, query: str) -> Optional[str]:
        if not self.is_cross_room_query(query):
            return None

        norm = normalize_turkish(query.lower())
        generic = (
            "odalarda" in norm
            and any(k in norm for k in ("proble", "problem", "sorun"))
            and not self.extract_issue_type(query)
        )
        if generic:
            return self.format_all_open_issues_summary(days=30)

        issue_type = self.extract_issue_type(query)
        if not issue_type:
            norm = normalize_turkish(query.lower())
            for itype in ("klima", "wifi", "priz", "tv", "temizlik"):
                if itype in norm:
                    issue_type = itype
                    break
        if not issue_type:
            return None

        rooms = self.find_rooms_with_open_issue(issue_type, days=30)
        if not rooms:
            return (
                f"🏨 **{issue_type.title()} sorunu bildirilen açık oda kaydı bulunmuyor.**\n\n"
                f"Son 30 günde bu tür bir sorun kaydı yok. Yeni şikayetler analiz edildiğinde "
                f"otomatik takip edilir."
            )

        lines = [f"🏨 **{issue_type.title()} sorunu olan odalar:**", ""]
        for room in rooms:
            status_tr = "planlandı" if room["status"] == "scheduled" else "açık"
            last = self._format_date_tr(room["last_reported"])
            lines.append(f"- **{room['entity_label']}**: {status_tr} (son bildirim: {last})")

        cross = self.find_cross_entity_patterns(issue_type, days=7)
        if len(cross) >= 2:
            labels = [p.get("entity_label", p.get("entity_id", "")) for p in cross if p.get("entity_type") == "room"]
            lines.append("")
            lines.append(
                f"⚠️ **Çapraz desen:** Aynı **{issue_type}** sorunu "
                f"{', '.join(labels)} odalarında eş zamanlı açık — sistemik problem olabilir."
            )

        return "\n".join(lines).strip()

    def format_entity_chat_answer(self, query: str) -> Optional[str]:
        if not self.is_entity_query(query):
            return None

        entity = self.extract_entity(query)
        if not entity:
            return None

        report = self.get_entity_report(entity["entity_id"])
        issues = report["issues"]
        label = entity.get("entity_label") or report["entity_label"]
        icon = self._entity_icon(report.get("entity_type", "facility"))

        if not issues and not report["comments"]:
            return (
                f"{icon} **{label}**\n\n"
                f"Şu an bu oda/birim için kayıtlı açık sorun görünmüyor. "
                f"Yeni bir bildirim olursa otomatik takip edilir.\n\n"
                f"Başka bir oda veya konu sormak isterseniz yazabilirsiniz."
            )

        lines = [f"{icon} **{label} — Operasyon Raporu**", ""]
        open_issues = [i for i in issues if i["status"] in ("open", "scheduled")]
        resolved_issues = [i for i in issues if i["status"] == "resolved"]

        if open_issues:
            lines.append("**Açık / devam eden sorunlar:**")
            for issue in open_issues:
                first = self._format_date_tr(issue["first_reported"])
                days_open = self._days_since(issue["first_reported"])
                status_tr = "planlandı" if issue["status"] == "scheduled" else "açık"
                detail = f"- **{issue['issue_type']}**: {days_open} gündür {status_tr}"
                if issue.get("scheduled_date"):
                    detail += f", {self._format_date_tr(issue['scheduled_date'])} servis planlandı"
                detail += f" (ilk: {first})"
                lines.append(detail)
            lines.append("")

        if resolved_issues:
            lines.append("**Çözülen sorunlar:**")
            for issue in resolved_issues:
                first = self._format_date_tr(issue["first_reported"])
                resolved = self._format_date_tr(issue.get("resolved_at") or issue["last_reported"])
                lines.append(f"- **{issue['issue_type']}**: {first} bildirildi, {resolved} giderildi")
            lines.append("")

        seen_patterns: set[str] = set()
        for issue in open_issues:
            itype = issue["issue_type"]
            if itype in seen_patterns:
                continue
            seen_patterns.add(itype)
            pattern = self.find_cross_entity_patterns(itype, days=7)
            other = [
                p for p in pattern
                if p.get("entity_id") != entity["entity_id"]
                and p.get("entity_type") == "room"
            ]
            if other:
                labels = [p.get("entity_label", p.get("entity_id", "")) for p in other]
                lines.append(
                    f"⚠️ **Çapraz desen:** Aynı **{itype}** sorunu "
                    f"{', '.join(labels)} birimlerinde de açık — sistemik problem olabilir."
                )
                lines.append("")

        if report["comments"]:
            lines.append("**Geçmiş kayıtlar:**")
            for c in report["comments"][-5:]:
                date_str = self._format_date_tr(c["created_at"])
                itype = c.get("issue_type") or "genel"
                flag = " (çözüldü)" if c.get("is_resolution") else ""
                lines.append(f"- {date_str} {itype}: \"{c['comment'][:80]}\"{flag}")

        return "\n".join(lines).strip()

    def format_room_chat_answer(self, query: str) -> Optional[str]:
        """Geriye dönük uyumluluk."""
        return self.format_entity_chat_answer(query)

    @staticmethod
    def _entity_icon(entity_type: str) -> str:
        icons = {
            "room": "🏨",
            "facility": "🏢",
            "service": "⚙️",
            "app": "📱",
            "shipment": "📦",
            "department": "🏛️",
        }
        return icons.get(entity_type, "📍")

    @staticmethod
    def _days_since(iso_value: str) -> int:
        dt = EntityTrackerService._parse_dt(iso_value)
        if not dt:
            return 0
        delta = datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)
        return max(0, delta.days)

    def _ensure_su_demo_seed(self) -> int:
        """Eski depolarda eksik kalan geçen hafta su sorunu kayıtlarını ekler."""
        existing_su = [
            i for i in self.store.all_issues()
            if i.issue_type == "su"
        ]
        if existing_su:
            return 0
        extras = [
            {"comment": "oda 218 de su basıncı çok düşük su sorunu var", "date": "2026-06-30T09:00:00+00:00"},
            {"comment": "218 nolu odada su arızası devam ediyor musluk akmıyor", "date": "2026-07-01T11:00:00+00:00"},
            {"comment": "oda 218 su sorunu düzeldi basınç normale döndü", "date": "2026-07-02T16:30:00+00:00"},
            {"comment": "oda 330 da su kaçırıyor banyo ıslak", "date": "2026-07-01T14:00:00+00:00"},
            {"comment": "330 nolu oda su sorunu giderildi tamir edildi", "date": "2026-07-03T10:00:00+00:00"},
        ]
        added = 0
        for entry in extras:
            self.register_from_comment(
                entry["comment"],
                review_id=f"demo-su-{added}",
                created_at=entry["date"],
            )
            added += 1
        return added

    def seed_demo_data(self, force: bool = False) -> dict[str, Any]:
        if force:
            self.store.clear()
        if self.store.count() > 0 and not force:
            extra = self._ensure_su_demo_seed()
            return {
                "seeded": extra,
                "total_issues": self.store.count(),
                "message": "Depo dolu" if extra == 0 else "Su demo eklendi",
            }

        demo_entries: list[dict[str, Any]] = [
            {"comment": "oda 101 te klima bozuk çalışmıyor", "date": "2026-07-07T09:00:00+00:00"},
            {"comment": "101 nolu odada klima arızası devam ediyor", "date": "2026-07-08T14:00:00+00:00"},
            {"comment": "oda 504 te priz çalışmıyor şarj edemiyorum", "date": "2026-07-03T10:00:00+00:00"},
            {"comment": "504 numaralı odada priz arızası devam ediyor", "date": "2026-07-03T14:30:00+00:00"},
            {"comment": "504 te priz tamir edildi düzeldi teşekkürler", "date": "2026-07-04T09:15:00+00:00"},
            {"comment": "oda 504 klima bozuk oda çok sıcak", "date": "2026-07-06T08:00:00+00:00"},
            {"comment": "504 nolu odada klima 3 gündür çalışmıyor", "date": "2026-07-07T11:00:00+00:00"},
            {"comment": "504 te klima arızası için 10.07.2026 teknik servis gelecek", "date": "2026-07-08T16:00:00+00:00"},
            {"comment": "702 numaralı odada klima bozuk gece uyuyamadık", "date": "2026-07-05T22:00:00+00:00"},
            {"comment": "oda 702 klima çalışmıyor hala düzelmedi", "date": "2026-07-07T09:30:00+00:00"},
            {"comment": "705 te klima arızalı çok sıcak", "date": "2026-07-06T13:00:00+00:00"},
            {"comment": "705 nolu oda kliması bozuk ikinci kez şikayet", "date": "2026-07-08T10:00:00+00:00"},
            {"comment": "301 numaralı odada wifi çalışmıyor", "date": "2026-07-02T15:00:00+00:00"},
            {"comment": "oda 301 wifi düzeldi artık bağlanıyor", "date": "2026-07-03T11:00:00+00:00"},
            {"comment": "412 te tv bozuk kumanda çalışmıyor", "date": "2026-07-04T20:00:00+00:00"},
            {"comment": "havuz küçüktü ve su çok soğuktu", "date": "2026-07-04T12:00:00+00:00"},
            {"comment": "havuzda hijyen sorunu var klor kokusu çok fazla", "date": "2026-07-06T09:00:00+00:00"},
            {"comment": "restoran çok iyiydi ama servis yavaştı", "date": "2026-07-05T19:00:00+00:00"},
            {"comment": "restoranda yemek soğuk geldi şikayet ettik", "date": "2026-07-06T20:00:00+00:00"},
            {"comment": "lobide wifi sürekli kopuyordu", "date": "2026-07-05T16:00:00+00:00"},
            {"comment": "lobide wifi düzeldi artık bağlanıyor", "date": "2026-07-08T10:00:00+00:00"},
            {"comment": "asansör bozuk 3. kata çıkamadık", "date": "2026-07-04T07:00:00+00:00"},
            {"comment": "asansör hala çalışmıyor ikinci şikayet", "date": "2026-07-07T18:00:00+00:00"},
            {"comment": "705 te klima arızalı çok sıcak", "date": "2026-07-06T13:00:00+00:00"},
            {"comment": "mobil uygulama çok yavaş açılmıyor", "date": "2026-07-07T10:00:00+00:00"},
            {"comment": "mobil uygulama donuyor sürekli kapanıyor", "date": "2026-07-08T14:00:00+00:00"},
            {"comment": "kargo teslimatı 5 gün gecikti TR12345678901", "date": "2026-07-03T08:00:00+00:00"},
            {"comment": "kargo TR12345678901 teslim edildi", "date": "2026-07-09T11:00:00+00:00"},
            {"comment": "internet sürekli kopuyordu wifi çalışmıyor", "date": "2026-07-07T20:00:00+00:00"},
            # Geçen hafta su sorunu (çözüldü) — issue_status_followup demosu
            {"comment": "oda 218 de su basıncı çok düşük su sorunu var", "date": "2026-06-30T09:00:00+00:00"},
            {"comment": "218 nolu odada su arızası devam ediyor musluk akmıyor", "date": "2026-07-01T11:00:00+00:00"},
            {"comment": "oda 218 su sorunu düzeldi basınç normale döndü", "date": "2026-07-02T16:30:00+00:00"},
            {"comment": "oda 330 da su kaçırıyor banyo ıslak", "date": "2026-07-01T14:00:00+00:00"},
            {"comment": "330 nolu oda su sorunu giderildi tamir edildi", "date": "2026-07-03T10:00:00+00:00"},
            # Oda 788 — tekrar eden klima (açık/çözülmüş karışık)
            {"comment": "oda 788 klima çalışmıyor çok sıcak", "date": "2026-06-28T10:00:00+00:00"},
            {"comment": "788 nolu odada klima düzeldi teşekkürler", "date": "2026-06-29T15:00:00+00:00"},
            {"comment": "oda 788 klima yine bozuldu ikinci kez", "date": "2026-07-05T22:00:00+00:00"},
            {"comment": "788 te klima hala çalışmıyor üçüncü şikayet", "date": "2026-07-08T09:00:00+00:00"},
            # Oda 102 — temizlik + su
            {"comment": "oda 102 çok kirli temizlik yapılmamış", "date": "2026-07-04T08:00:00+00:00"},
            {"comment": "102 nolu oda temizlendi düzeldi", "date": "2026-07-04T14:00:00+00:00"},
            {"comment": "oda 102 su basıncı düşük", "date": "2026-07-07T11:00:00+00:00"},
            # Oda 215 — açık klima
            {"comment": "oda 215 klima soğutmuyor", "date": "2026-07-08T16:00:00+00:00"},
            # Oda 605 — wifi çözüldü
            {"comment": "oda 605 wifi çalışmıyor", "date": "2026-07-06T12:00:00+00:00"},
            {"comment": "605 te wifi düzeldi", "date": "2026-07-07T09:00:00+00:00"},
        ]

        added = 0
        for entry in demo_entries:
            self.register_from_comment(
                entry["comment"],
                review_id=f"demo-entity-{added}",
                created_at=entry["date"],
            )
            added += 1

        entities = sorted({i.entity_id for i in self.store.all_issues()})
        rooms = sorted({
            i.room_number for i in self.store.all_issues()
            if i.room_number
        })
        return {
            "seeded": added,
            "total_issues": self.store.count(),
            "entities": entities,
            "rooms": rooms,
        }


_service: Optional[EntityTrackerService] = None


def get_entity_tracker_service() -> EntityTrackerService:
    global _service
    if _service is None:
        _service = EntityTrackerService()
    return _service
