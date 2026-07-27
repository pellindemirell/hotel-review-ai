"""
Systemic ABSA clause pipeline — config-driven stages.

Stages:
  1. Segment (caller may pass pre-split clauses)
  2. Meta / noise filter
  3. Context frame detection
  4. Aspect + sentiment with frame
  5. Department + anti-pattern guards
  6. Severity policy
  7. Summary builder

Prefer extending config/absa/clause_pipeline.yaml over Crystal-specific if/else.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

import yaml

from app.services.turkish_nlp_utils import normalize_turkish

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "absa", "clause_pipeline.yaml"
)


def _fold(text: str) -> str:
    t = normalize_turkish(text or "").lower()
    return (
        t.replace("ı", "i")
        .replace("İ", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )


@lru_cache(maxsize=1)
def load_pipeline_config() -> dict[str, Any]:
    path = os.path.abspath(_CONFIG_PATH)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_pipeline_config() -> dict[str, Any]:
    load_pipeline_config.cache_clear()
    return load_pipeline_config()


@dataclass
class ClauseDecision:
    clause: str
    include: bool = True
    drop_reason: str = ""
    frame: str = "general"
    aspect_key: str = "general"
    aspect_label: str = "Genel"
    department: str = "genel"
    department_label: str = "Genel"
    category: str = "Genel"
    sentiment: str = "Neutral"
    sentiment_score: float = 0.0
    priority: str = "medium"
    priority_score: int = 2
    confidence: float = 0.75
    method: str = "clause_pipeline"
    frame_scores: dict[str, float] = field(default_factory=dict)
    overrides: list[str] = field(default_factory=list)


def _cue_str(c: Any) -> str:
    """YAML may parse 18.00 as float — always coerce cues to string."""
    if c is None:
        return ""
    if isinstance(c, float):
        # 18.0 → "18.00" if looks like clock, else str
        s = f"{c:.2f}" if c == int(c) or abs(c - int(c)) < 1e-9 else str(c)
        if s.endswith(".00") and len(s) <= 5:
            return s
        return str(c)
    return str(c)


def _match_cue(text: str, folded: str, cs: str) -> bool:
    cs_low = cs.lower()
    cs_fold = _fold(cs)
    if cs_low.startswith(r"\b") or cs_low.endswith(r"\b"):
        return bool(re.search(cs_low, text) or re.search(cs_fold, folded))
    if len(cs_low) <= 4:
        pattern_text = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_low)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        pattern_fold = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_fold)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        return bool(re.search(pattern_text, text) or re.search(pattern_fold, folded))
    return cs_low in text or cs_fold in folded


def _any_cue(text: str, folded: str, cues: list) -> bool:
    for c in cues or []:
        cs = _cue_str(c)
        if not cs:
            continue
        # Positive whitelist trap: "bekle" ⊂ "beklemeden"
        if cs.lower() in ("bekle",) and ("beklemeden" in text or "beklemeden" in folded):
            continue
        if _match_cue(text, folded, cs):
            return True
    return False


def _count_cues(text: str, folded: str, cues: list) -> int:
    n = 0
    for c in cues or []:
        cs = _cue_str(c)
        if not cs:
            continue
        if cs.lower() in ("bekle",) and ("beklemeden" in text or "beklemeden" in folded):
            continue
        if _match_cue(text, folded, cs):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Stage 2 — meta / noise
# ---------------------------------------------------------------------------
def has_operational_rescue(clause: str, cfg: Optional[dict] = None) -> bool:
    """Long narrative openers that also carry queue/capacity signals must be kept."""
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    min_words = int(cfg.get("meta_rescue_min_words", 8))
    if len(clause.split()) < min_words:
        return False
    return _any_cue(low, folded, cfg.get("meta_rescue_cues") or [])


def is_meta_clause(clause: str, cfg: Optional[dict] = None) -> bool:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    matched_meta = False
    for p in cfg.get("meta_patterns") or []:
        if ".*" in p:
            if re.search(p, low, flags=re.IGNORECASE) or re.search(_fold(p), folded):
                matched_meta = True
                break
        elif p.lower() in low or _fold(p) in folded:
            matched_meta = True
            break
    if matched_meta:
        # Do not drop queue/exhaustion/capacity complaints glued to framing
        if has_operational_rescue(clause, cfg):
            return False
        return True
    # Short demographic-only
    demo = cfg.get("demographic_patterns") or []
    if _any_cue(low, folded, demo) and len(clause.split()) <= 12:
        if not _any_cue(low, folded, ["kötü", "kotu", "berbat", "şikayet", "sikayet"]):
            if not has_operational_rescue(clause, cfg):
                return True
    return False


def is_thanks_clause(clause: str, cfg: Optional[dict] = None) -> bool:
    cfg = cfg or load_pipeline_config()
    return _any_cue(clause.lower(), _fold(clause), cfg.get("thanks_patterns") or [])


# ---------------------------------------------------------------------------
# Stage 3 — frames
# ---------------------------------------------------------------------------
def detect_frames(clause: str, cfg: Optional[dict] = None) -> dict[str, float]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    frames_cfg = cfg.get("frames") or {}
    scores: dict[str, float] = {}

    for name, spec in frames_cfg.items():
        score = 0.0
        score += 1.5 * _count_cues(low, folded, spec.get("entity_cues") or [])
        for key, weight in (
            ("size_cues", 2.0),
            ("hygiene_cues", 2.0),
            ("noise_cues", 2.5),
            ("table_service_cues", 2.5),
            ("quantity_cues", 1.5),
            ("variety_cues", 2.0),
            ("hours_cues", 1.5),
            ("lounger_cues", 2.5),
            ("cleaning_soda_cues", -5.0),
        ):
            score += weight * _count_cues(low, folded, spec.get(key) or [])
        if score > 0:
            scores[name] = score

    # Structural: N kişilik sıra / kuyruk always queue
    if re.search(r"\d+\s*ki[sş]ilik", low) and any(w in folded for w in ("sira", "kuyruk", "bekle")):
        scores["queue"] = scores.get("queue", 0) + 4.0
    if any(w in folded for w in ("kuyruk", "sirayi bekle", "sira bekle", "sira bekleniyor", "beklemis", "beklemiş")):
        scores["queue"] = scores.get("queue", 0) + 2.0
    # Drink + wait minutes → queue dominates drink quality
    if (any(w in folded for w in ("icecek", "içecek", "limonata", "tekila")) or _any_cue(low, folded, ["bar"])) and any(
        w in folded for w in ("sira", "kuyruk", "dakika", "bekle", "alinamiyor", "alınamıyor")
    ):
        scores["queue"] = scores.get("queue", 0) + 3.5
    # Pool lounger queue
    if any(w in folded for w in ("sezlong", "şezlong")) and any(w in folded for w in ("sira", "kuyruk", "bekle", "bulunmuyor", "yok")):
        scores["pool"] = scores.get("pool", 0) + 3.0
        scores["queue"] = scores.get("queue", 0) + 2.0
    # Distance to pool sarcasm — suppress hygiene/pool dominance
    if "metre" in folded and "havuz" in folded and any(
        w in folded for w in ("yuru", "kos", "isterseniz", "guzel bir yani yok")
    ):
        scores["pool"] = max(0.0, scores.get("pool", 0) - 6.0)
        scores["value"] = scores.get("value", 0) + 2.0

    # Beverage soda / limonata — never lose to weak room score
    bar_spec = frames_cfg.get("bar") or {}
    if re.search(r"(?<![a-z])soda(?![a-z])", folded) and not _any_cue(
        low, folded, bar_spec.get("cleaning_soda_cues") or []
    ):
        scores["bar"] = scores.get("bar", 0) + 3.5
    if any(w in folded for w in ("limonata", "barda ", "tekila", "alkol")) or _any_cue(low, folded, ["bar"]):
        scores["bar"] = scores.get("bar", 0) + 1.5

    # "aynı durum X için geçerli" inherits drink/queue context words in clause
    if ("ayni durum" in folded or "aynı durum" in low) and re.search(r"(?<![a-z])soda(?![a-z])", folded):
        scores["bar"] = scores.get("bar", 0) + 4.0

    # "restoran bar / restoran bar veya" → fb_venue not bar
    if "restoran" in folded and _any_cue(low, folded, ["bar"]):
        if any(w in folded for w in ("veya", "ve", "arası", "arasi", "diger", "diğer")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 4.0
            scores["bar"] = 0.0

    # "restoran bar restoran bar veya" → her iki kuralı birleştir - fb_venue kazansın
    # (üstteki veya/ve/arası kontrolü öncelikli)

    # Personel + uzun çalışma saatleri → personel (not restaurant)
    if any(w in folded for w in ("personel", "calisan", "çalışan")) and any(
        w in folded for w in ("saat", "vardiya", "mesai", "calisiyor", "çalışıyor")
    ):
        scores["staff"] = scores.get("staff", 0) + 3.0

    # "restoran bar" → fb_venue not bar
    if "restoran" in folded and _any_cue(low, folded, ["bar"]):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0
        scores["bar"] = scores.get("bar", 0) - 3.0

    # Bardak + yemek/yağ context → fb_venue not bar
    if "bardak" in folded and any(w in folded for w in ("yag", "yağ", "leke", "kirli", "bulasik", "bulaşık")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0
        scores["bar"] = scores.get("bar", 0) - 2.0

    # Saç kurutma makinesi → housekeeping (not teknik)
    if any(w in folded for w in ("sac kurutma", "saç kurutma", "fön", "fon")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 3.0

    # Havuz temiz → pool, not spa (masaj keyword override)
    if any(w in folded for w in ("havuz",)) and _any_cue(low, folded, ["temiz", "kirli", "pis", "buyuk", "büyük", "güzel", "guzel"]):
        if any(w in folded for w in ("masaj", "spa")):
            scores["pool"] = max(scores.get("pool", 0), scores.get("spa_wellness", 0) + 3.0)

    # "iki büyük havuz / havuz da temizdi" → pool not room or housekeeping
    if any(w in folded for w in ("havuz",)) and not _any_cue(low, folded, ["oda", "banyo"]):
        if any(w in folded for w in ("buyuk", "büyük", "temiz", "güzel", "guzel")):
            scores["room"] = max(0.0, scores.get("room", 0) - 3.0)
            scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # Klima filtre → teknik not housekeeping
    if any(w in folded for w in ("klima",)) and any(w in folded for w in ("filtre", "toz", "ufle", "üfle")):
        scores["tech"] = scores.get("tech", 0) + 3.0

    # Sular kesildi, sıcak su, duş basıncı → tech (not housekeeping)
    if any(w in folded for w in ("sicak su", "sıcak su", "su kes", "sular kes", "dus basinc", "duş basınç", "basinc", "basınç", "su gelmiyor")):
        scores["tech"] = scores.get("tech", 0) + 4.0
        scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # Food smell → fb_venue (not housekeeping)
    if "koku" in folded and any(w in folded for w in ("yemek", "balik", "balık", "tabak", "tabag", "mutfak", "restoran", "restaurant", "bufe", "büfe")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0
        scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # "temizlik personeli / güvenlik personeli" → personel behavior
    if any(w in folded for w in ("personel", "personeli", "calisan", "çalışan", "görevlisi", "gorevlisi")):
        if any(w in folded for w in ("kapıyı çalmadan", "kapiyi calmadan", "kapiyi çalmadan", "kapıyı calmadan",
                                     "calmadan girdi", "çalmadan girdi", "kibar", "yardimci", "yardımcı",
                                     "ilgili", "aktif", "nazik", "ilgisiz", "kaba", "yorgun")):
            scores["staff"] = scores.get("staff", 0) + 3.0

    # Havuz bağlamında "sıra beklemiyorsunuz" positive → pool
    if any(w in folded for w in ("havuz", "aquapark", "plaj")):
        if "beklemiyor" in folded or "beklemeden" in folded:
            scores["pool"] = scores.get("pool", 0) + 2.0
    # Havuz/aquapark + mesafe/restoran → pool (not restaurant)
    if any(w in folded for w in ("aquapark", "plaj", "havuz")) and any(
        w in folded for w in ("mesafe", "arası", "arasi", "restoran", "pastane")
    ):
        scores["pool"] = scores.get("pool", 0) + 3.0

    # Spa + randevu/bekleme → spa (not queue/restaurant)
    if any(w in folded for w in ("spa", "masaj", "sauna", "hamam", "wellness")) and any(
        w in folded for w in ("randevu", "bekledik", "beklemek", "gunlerce", "günlerce", "rezervasyon")
    ):
        scores["spa_wellness"] = scores.get("spa_wellness", 0) + 5.0
        scores["queue"] = max(0.0, scores.get("queue", 0) - 4.0)

    # Minibar ücreti → Front Office
    if "minibar" in folded and any(w in folded for w in ("ucret", "ücret", "fahis", "fahiş", "pahali", "pahalı")):
        scores["front_office"] = scores.get("front_office", 0) + 4.0

    # "bayıldım" → restaurant (food praise), not personel
    praise_food = any(w in folded for w in ("bayildim", "bayıldım", "harikaydi", "harikaydı"))
    if praise_food and any(w in folded for w in ("yemek", "corba", "çorba", "dolma", "kofte", "köfte", "pizza", "makarna", "salam")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0

    # "salam tabağında sinek" → restaurant, not room
    if any(w in folded for w in ("salam", "tabak", "tabağında")):
        if any(w in folded for w in ("sinek", "bocek", "böcek", "kirli")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 4.0

    # "kumanda odada yoktu resepsiyondan istedik" → teknik (not FO)
    if any(w in folded for w in ("kumanda", "tv", "televizyon")):
        if "resepsiyon" in folded or "istedik" in folded:
            scores["tech"] = scores.get("tech", 0) + 3.0

    # "odalar daha bakımlı" → housekeeping (not room)
    if _any_cue(low, folded, ["oda"]) and any(w in folded for w in ("bakim", "bakım", "bakimli", "bakımlı")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 3.0

    # "canlı pişirme istasyonu" → restaurant not housekeeping
    if any(w in folded for w in ("pisirme", "pişirme", "istasyon", "mutfak")):
        if any(w in folded for w in ("canli", "canlı", "kapali", "kapalı")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0

    # "glutensiz seçenek" / "kimse yardımcı olamadı" → restaurant (food service failure)
    if any(w in folded for w in ("glutensiz", "vejetaryen", "vejeteryan")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0

    # "çeşitlilik" without bar context → restaurant
    food_ctx = any(w in folded for w in ("yemek", "kahvalti", "kahvaltı", "bufe", "büfe", "restoran"))
    if ("çeşit" in folded or "cesit" in folded) and not (any(w in folded for w in ("alkol", "icecek", "içecek", "tekila", "bira", "sarap", "şarap")) or _any_cue(low, folded, ["bar"])):
        if food_ctx:
            scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0
        elif not food_ctx:
            scores["bar"] = scores.get("bar", 0) - 1.0

    # Front Office boost: check-in/resepsiyon + bekle/kuyruk/saat → FO dominates queue
    if any(w in folded for w in ("check-in", "checkin", "check-out", "checkout", "resepsiyon", "lobi")):
        if any(w in folded for w in ("bekle", "sira", "sıra", "kuyruk", "saat", "dakika", "yarim", "yavaş", "yavas")):
            scores["front_office"] = scores.get("front_office", 0) + 4.0

    # Staff + drink context → personnel behavior dominates bar quality
    staff_keywords = ("garson", "personel", "calisan", "çalışan", "barmen", "servis ekibi")
    if any(w in folded for w in staff_keywords):
        if any(w in folded for w in ("icecek", "içecek", "kokteyl", "soda", "barda", "siparis", "sipariş")) or _any_cue(low, folded, ["bar"]):
            scores["staff"] = scores.get("staff", 0) + 4.0
            scores["bar"] = max(0.0, scores.get("bar", 0) - 3.0)
    # Personel attitude + "istemeyerek" → strong staff signal
    if any(w in folded for w in ("istemeyerek", "isteyerek yapmiyor", "isteyerek yapmıyor", "sormasi", "sorması")):
        scores["staff"] = scores.get("staff", 0) + 4.0

    # ANTI-PATTERN: "sef" in "seferinde/seferlik/sefa" → false staff match
    if any(w in folded for w in ("seferinde", "seferlik", "sefa")):
        scores["staff"] = max(0.0, scores.get("staff", 0) - 3.0)
    # ANTI-PATTERN: "yardımcı olamadı/olamıyor/olamaz" → not staff (unable to help)
    if any(w in folded for w in ("olamadi", "olamadı", "olamiyor", "olamıyor", "olamaz", "olmuyor", "yoktu")):
        if "yardimci" in folded or "yardımcı" in low:
            scores["staff"] = max(0.0, scores.get("staff", 0) - 3.0)
    # ANTI-PATTERN: "bar" in "minibar" → false bar match
    if "minibar" in folded and scores.get("bar", 0) > 0:
        # If only bar cue match is from "bar" in "minibar", strip it
        if scores.get("bar", 0) <= 3.0 and scores.get("staff", 0) <= 1.0:
            scores["bar"] = max(0.0, scores["bar"] - 1.5)

    # Housekeeping structural boosts
    if any(w in folded for w in ("koridor", "koridorlarda")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 2.0
    if any(w in folded for w in ("kuş yuvası", "kus yuvasi", "kuş yuvası")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 5.0
    if any(w in folded for w in ("pike", "yastik", "yastık", "nevresim")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 2.0

    if "masa tenisi" in folded:
        scores["animation"] = scores.get("animation", 0) + 4.0

    return scores


def primary_frame(scores: dict[str, float]) -> str:
    if not scores:
        return "general"
    # Prefer operational specificity when scores are close
    priority = (
        "front_office", "spa_wellness", "queue", "pool", "capacity",
        "housekeeping", "bar", "fb_venue", "tech",
        "value", "staff", "animation", "room",
        "environment", "general",
    )
    best = max(scores.values())
    contenders = [k for k, v in scores.items() if v >= best - 0.75]
    for name in priority:
        if name in contenders:
            return name
    return max(scores.items(), key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Stage 4 — aspect typing within frame
# ---------------------------------------------------------------------------
def resolve_aspect(
    clause: str,
    frame: str,
    frame_scores: dict[str, float],
    cfg: Optional[dict] = None,
) -> dict[str, str]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    frames = cfg.get("frames") or {}
    aspects = cfg.get("aspect_resolution") or {}

    def pick(key: str) -> dict[str, str]:
        return dict(aspects.get(key) or {
            "aspect_key": key,
            "aspect_label": key,
            "department": "genel",
            "department_label": "Genel",
            "category": "Genel",
        })

    room = frames.get("room") or {}
    fb = frames.get("fb_venue") or {}
    bar = frames.get("bar") or {}
    pool = frames.get("pool") or {}

    queueish = (
        frame == "queue"
        or frame_scores.get("queue", 0) >= 2
        or _any_cue(
            low, folded,
            ["kuyruk", "sira", "sıra", "siraya", "sıraya", "sirayi", "sırayı", "bekleniyor", "alinamiyor", "alınamıyor"],
        )
    )
    poolish = (
        frame == "pool"
        or frame_scores.get("pool", 0) >= 2
        or _any_cue(low, folded, pool.get("entity_cues") or [])
        or _any_cue(low, folded, pool.get("lounger_cues") or [])
    )

    # Distance sarcasm ("500 metre yürümek… güzel") — check BEFORE room / housekeeping
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []) or (
        ("metre" in folded or "yuru" in folded or "yürü" in low or "ucunda" in folded) and
        ("kosmak" in folded or "koşmak" in low or "isterseniz" in folded or "guzel" in folded)
    ):
        return pick("guest_experience")

    # Staff must be checked before drink/food leftovers
    if frame == "staff" or frame_scores.get("staff", 0) >= 2:
        # EXCEPTION 4: animation keywords in staff (e.g. animasyon ekibi)
        if _any_cue(low, folded, ["animasyon", "animasyon ekibi", "animasyon ekibinden", "animasyoncu", "eğlence", "eglence", "eğlenceli", "eglenceli"]):
            return pick("animation")
        # EXCEPTION 1: kids club → animation (not personel)
        if _any_cue(low, folded, ["kids club", "cocuk kulub", "çocuk kulüb", "cocuk klub", "çocuk klub"]):
            return pick("animation")
        # EXCEPTION 3: müşteri temsilcisi → Genel (not personel)
        if _any_cue(low, folded, ["musteri temsilcisi", "müşteri temsilcisi"]):
            return pick("general")
        # EXCEPTION 2: restaurant/food context dominates staff
        if _any_cue(low, folded, ["glutensiz", "vejetaryen", "vejeteryan", "seçenek", "secenek",
                                   "yemek", "corba", "çorba", "restoran", "restaurant",
                                   "menu", "menü", "child menu", "çocuk menü"]):
            if not _any_cue(low, folded, ["kaba", "ilgisiz", "sormasi", "sorması", "istemeyerek",
                                           "kapıyı", "kapiyi", "davran"]) and \
               not _any_cue(low, folded, ["yardımcı", "yardimci", "yardım"]) and \
               not any(w in folded for w in ("personel az", "personel yetersiz")):
                pass  # fall through to restaurant
            else:
                return pick("staff_behavior")
        else:
            return pick("staff_behavior")

    # --- FRONT OFFICE: check-in, resepsiyon, fatura, concierge etc. ---
    fo_score = frame_scores.get("front_office", 0)
    if frame == "front_office" or fo_score >= 2:
        return pick("front_office")

    # --- SPA / WELLNESS: masaj, sauna, hamam, jakuzi, fitness ---
    spa_score = frame_scores.get("spa_wellness", 0)
    if frame == "spa_wellness" or spa_score >= 2:
        # EXCEPTION: havuz + masaj → pool wins when "havuz" is explicit and "masaj" is secondary
        pool_score = frame_scores.get("pool", 0)
        if pool_score >= 2 and _any_cue(low, folded, ["havuz"]) and not _any_cue(low, folded, ["spa merkezi", "spa merkezinde"]):
            return pick("pool_lounger")
        return pick("spa")

    # --- HOUSEKEEPING: temizlik, havlu, çarşaf, koridor, çöp etc. ---
    # Noise / soundproofing must pick room_noise before generic housekeeping_service
    if _any_cue(low, folded, ["ses yalıtım", "ses yalit", "yan oda", "ses geçiyor", "ses geciyor", "ses yalıtımı"]):
        return pick("room_noise")

    hk_score = frame_scores.get("housekeeping", 0)
    # Minibar context: "minibar doldur" → housekeeping, "minibar soğutmuyor" → teknik
    # "mini barı çok yetersiz" / "sadece alkolsüz içecek" → Bar (not HK or Restaurant)
    if _any_cue(low, folded, ["minibar", "mini bar"]):
        if _any_cue(low, folded, ["sogut", "soğut", "bozuk", "ilik", "ılık", "calismi", "çalışmı"]):
            return pick("minibar_tech")
        if _any_cue(low, folded, ["doldur", "ikmal", "doldurul"]):
            return pick("minibar_supply")
        if _any_cue(low, folded, ["yetersiz", "sadece", "az ", "eksik", "kısıtlı", "kisitli", "kotu", "kötü"]):
            # EXCEPTION: "sadece minibar görevlisi" → staff/service context, not drink variety
            if "gorevlisi" not in folded and "görevlisi" not in low:
                return pick("drink_variety")
    if frame == "housekeeping" or hk_score >= 3:
        # Exclude cases where noise or tech is dominant
        tech_score = frame_scores.get("tech", 0)
        if tech_score > hk_score:
            pass  # fall through to tech handling below
        else:
            return pick("housekeeping_service")

    # --- ANIMATION: must check BEFORE room noise to avoid misclassification ---
    if (frame == "animation" or frame_scores.get("animation", 0) >= 2) and not _any_cue(low, folded, ["aquapark", "aquaprk", "havuz", "plaj"]):
        return pick("animation")
    # Explicit animasyon/show/konser keywords even with noise → animation dept
    if _any_cue(low, folded, ["animasyon", "animator", "show", "konser", "etkinlik", "aktivite", "kids club"]) and not _any_cue(low, folded, ["aquapark", "aquaprk", "havuz", "plaj"]):
        if not _any_cue(low, folded, ["spa", "masaj", "sauna"]):
            return pick("animation")

    # QUEUE first — drink wait is Servis/Kuyruk, never İçecek Kalitesi
    if queueish:
        # Resepsiyon / Check-in queue → Front Office (never F&B Restaurant Servis/Kuyruk)
        if _any_cue(low, folded, ["check-in", "checkin", "check-out", "checkout", "resepsiyon", "lobi"]):
            return pick("front_office")
        # Sunbed/pool wait → Havuz / Aktivite (never F&B Restaurant Servis/Kuyruk)
        if _any_cue(low, folded, ["sezlong", "şezlong", "lounger"]):
            return pick("pool_lounger")
        # İçecek + kuyruk/sıra → Servis/Kuyruk (never İçecek Kalitesi)
        return pick("service_queue")

    # Distance sarcasm ("500 metre yürümek… güzel") — not pool hygiene
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []) and (
        "metre" in folded or "yuru" in folded or "yürü" in low
    ):
        return pick("guest_experience")

    # Pool lounger without explicit queue noun
    if poolish and _any_cue(low, folded, pool.get("lounger_cues") or []):
        return pick("pool_lounger")
    # Pool hygiene/quality (frame=pool, not spa)
    if poolish and (any(w in folded for w in ("temiz", "kirli", "pis", "bakımlı", "derin", "soguk", "sıcak", "ısı", "isi",
                                                "clean", "dirty", "cold", "warm", "deep", "nice", "beautiful")) or
                    any(w in low for w in ("güzel", "harika", "berbat", "kötü", "kotu", "nice", "beautiful", "great"))):
        return pick("pool_lounger")
    # Pool + mesafe/distance → pool (not restaurant)
    if poolish and any(w in folded for w in ("mesafe", "arası", "arasi")):
        return pick("pool_lounger")

    # ROOM: noise / size / cleanliness
    if frame == "room" or (frame_scores.get("room", 0) >= 2 and (_any_cue(low, folded, ["oda"]) or "room" in folded)):
        if _any_cue(low, folded, room.get("noise_cues") or []):
            return pick("room_noise")
        if _any_cue(low, folded, room.get("size_cues") or []):
            if not _any_cue(low, folded, room.get("hygiene_cues") or []):
                return pick("room_size")
        if _any_cue(low, folded, room.get("hygiene_cues") or []):
            return pick("room_cleanliness")
        if _any_cue(low, folded, room.get("size_cues") or []):
            return pick("room_size")

    # F&B venue: table cleaning / cutlery / food / meat
    if frame == "fb_venue" or frame_scores.get("fb_venue", 0) >= 2:
        # EXCEPTION: staff behavior in fb_venue (e.g. garson, şef, personel, çalışan, barmen)
        if _any_cue(low, folded, ["garson", "barmen", "şef", "sef", "şefi", "sefi", "personel", "calisan", "çalışan"]):
            if _any_cue(low, folded, ["ilgi", "kaba", "yavas", "yavaş", "temiz", "guler", "güler", "isteme", "davran", "kibar", "saygi", "saygı", "umursamaz"]):
                return pick("staff_behavior")

        if _any_cue(low, folded, ["catal", "çatal", "bicak", "bıçak"]):
            return pick("cutlery")
        if _any_cue(low, folded, fb.get("table_service_cues") or []) or (
            "masa" in folded and _any_cue(low, folded, ["temiz", "kirli", "sil"])
        ):
            return pick("table_cleanliness")
        if "kiyma" in folded or "kıyma" in low:
            return pick("meat_quality")
        if _any_cue(low, folded, ["lezzet", "yemek", "tat", "breakfast", "dinner", "lunch", "food", "taste", "meal", "dish"]):
            return pick("food_taste")
        # Catch-all: any fb_venue match defaults to food_taste
        if frame == "fb_venue":
            return pick("food_taste")

    # BAR: variety (hours/konsept) before bare drink quality
    # Bardak + yag/leke → restaurant table cleanliness
    if "bardak" in folded and any(w in folded for w in ("yag", "yağ", "leke", "lekeli", "kirli")):
        return pick("table_cleanliness")
    # Bare "çeşitlilik arttırılmalı / çeşit" → restaurant (always)
    if _any_cue(low, folded, ["çeşitlilik", "cesitlilik", "çeşit", "cesit"]):
        if not (any(w in folded for w in ("alkol", "barda", "icecek", "içecek", "tekila", "sarap", "şarap", "bira", "kokteyl")) or _any_cue(low, folded, ["bar"])):
            return pick("food_taste")
    # Guard: "çeşit/çeşitlilik" with food context (kahvaltı, büfe, yemek, bal, kaymak, dondurma) stays Restaurant
    food_context = _any_cue(low, folded, [
        "kahvalti", "kahvaltı", "bufe", "büfe", "yemek", "bal ", "kaymak",
        "dondurma", "peynir", "zeytin", "tatlı", "tatli", "pasta", "salata",
        "corba", "çorba", "balik", "balık", "et ", "sebze", "meyve",
        "vejeteryan", "vejetaryen", "glutensiz", "pisirme", "pişirme",
        # English food context
        "breakfast", "dinner", "lunch", "food", "meal", "dish", "taste",
        "buffet", "menu", "dessert", "soup", "salad", "bread", "cheese",
        "meat", "chicken", "pizza", "pasta", "rice", "fish", "fruit",
    ])
    bardak_food = "bardak" in folded and food_context
    if (frame == "bar" or frame_scores.get("bar", 0) >= 2) and not food_context and not bardak_food:
        if not _any_cue(low, folded, bar.get("cleaning_soda_cues") or []):
            if _any_cue(low, folded, bar.get("variety_cues") or []) or _any_cue(
                low, folded, bar.get("hours_cues") or []
            ) or _any_cue(
                low, folded,
                ["tekila", "sadece belli", "belli bar", "konsept", "cesit alkol", "çeşit alkol", "7/24"],
            ):
                return pick("drink_variety")
            if re.search(r"(?<![a-z])soda(?![a-z])", folded) or _any_cue(
                low, folded,
                ["limonata", "icecek", "içecek", "barda", "kokteyl", "sarap", "şarap", "raki", "rakı", "bira", "alkol"],
            ):
                return pick("drink_quality")

    # Orphan drink fragment after "ve" split: "şaraplar bence kalitesiz"
    if _any_cue(low, folded, ["sarap", "şarap", "raki", "rakı", "tekila", "bira", "kokteyl"]):
        if _any_cue(low, folded, ["kalitesiz", "kotu", "kötü", "berbat", "yetersiz", "yok"]):
            return pick("drink_quality")
        if not food_context:
            return pick("drink_quality")

    if frame == "tech" or frame_scores.get("tech", 0) >= 2:
        if _any_cue(low, folded, ["wifi", "wi-fi", "internet", "baglan", "bağlan"]):
            return pick("wifi")
        # Generic tech issues (klima, elektrik, lavabo etc.)
        return pick("tech_general")

    if frame == "capacity" or frame_scores.get("capacity", 0) >= 2:
        if _any_cue(low, folded, ["kuyruk", "sira", "sıra", "bekle", "kişilik", "kisilik"]):
            return pick("service_queue")
        return pick("capacity")

    if frame == "value" or frame_scores.get("value", 0) >= 2:
        if _any_cue(low, folded, ["pişman", "pisman", "çöp", "cop", "değmez", "degmez", "çarçur", "carcur"]):
            return pick("value_for_money")
        return pick("guest_experience")

    if frame == "staff" or frame_scores.get("staff", 0) >= 2:
        return pick("staff_behavior")

    # --- ENVIRONMENT / CEVRE: konum, otopark, guvenlik, ulasim, manzara ---
    env_score = frame_scores.get("environment", 0)
    if frame == "environment" or env_score >= 1.5:
        if _any_cue(low, folded, ["otopark", "park yeri", "park yeri", "garaj", "valet", "arac", "araç"]):
            return pick("parking")
        if _any_cue(low, folded, ["transfer", "servis", "ulasim", "ulaşım", "metro", "otobus", "otobüs",
                                   "minibus", "minibüs", "taksi", "havaalani", "havaalanı", "havalimani", "havalimanı",
                                   "istasyon", "duragi", "durağı", "yurume", "yürüme"]):
            return pick("transport")
        if _any_cue(low, folded, ["guvenlik", "güvenlik", "guvenlikci", "güvenlikçi", "huzur"]):
            return pick("safety")
        if _any_cue(low, folded, ["konum", "lokasyon", "yer ", "merkez", "manzara", "deniz", "sahil",
                                   "bahce", "bahçe", "yesil", "yeşil", "cevre", "çevre", "dogal", "doğal"]):
            return pick("location")
        if _any_cue(low, folded, ["yakın", "yakin", "uzak", "sessiz", "sapa"]):
            return pick("location")
        return pick("location")

    # Heuristic leftovers — check for explicit keywords without strong frame
    # Front office leftovers
    if _any_cue(low, folded, ["check-in", "check-out", "checkin", "checkout", "resepsiyon", "fatura", "depozito",
                              "oda karti", "oda kartı", "concierge", "lobi", "overbooking", "transfer",
                              "bilgilendirme", "yonlendirme", "yönlendirme", "yon tabela", "yön tabela"]):
        return pick("front_office")
    # Spa leftovers
    if _any_cue(low, folded, ["spa", "masaj", "sauna", "hamam", "jakuzi", "wellness", "fitness", "kese"]):
        return pick("spa")
    # Housekeeping leftovers
    if _any_cue(low, folded, ["koridor", "tuvalet kagidi", "tuvalet kağıdı", "cop kutusu", "çöp kutusu",
                              "yastik", "yastık", "pike", "nevresim", "umumi"]):
        return pick("housekeeping_service")
    if _any_cue(low, folded, room.get("noise_cues") or []):
        return pick("room_noise")
    if _any_cue(low, folded, room.get("size_cues") or []) and _any_cue(low, folded, ["oda"]):
        return pick("room_size")
    if "masa" in folded and _any_cue(low, folded, ["temizletemed", "temiz", "kirli"]):
        return pick("table_cleanliness")
    if _any_cue(low, folded, ["wifi", "wi-fi"]) and _any_cue(low, folded, ["baglan", "bağlan", "asla"]):
        return pick("wifi")
    if _any_cue(low, folded, ["kuyruk", "sira", "sıra", "bekle"]):
        return pick("service_queue")
    if _any_cue(low, folded, ["hersey dahil", "herşey dahil", "karisik", "karışık", "yorucu", "yorgunluk"]):
        return pick("capacity")
    # Environment leftovers
    if _any_cue(low, folded, ["konum", "lokasyon", "otopark", "guvenlik", "güvenlik",
                              "manzara", "ulasim", "ulaşım", "transfer", "bahce", "bahçe",
                              "deniz", "sahil", "metro"]):
        return pick("location")
    # Food-related leftovers
    if food_context:
        return pick("food_taste")

    return pick("guest_experience") if frame != "general" else {
        "aspect_key": "general",
        "aspect_label": "Genel",
        "department": "genel",
        "department_label": "Genel",
        "category": "Genel",
    }


# ---------------------------------------------------------------------------
# Stage 4b — sentiment modifiers
# ---------------------------------------------------------------------------
def apply_sentiment_modifiers(
    clause: str,
    sentiment: str,
    score: float,
    frame: str,
    aspect_key: str,
    cfg: Optional[dict] = None,
) -> tuple[str, float, list[str]]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    notes: list[str] = []

    mediocre = cfg.get("mediocre_lexicon") or []
    if _any_cue(low, folded, mediocre):
        # Never leave Positive when mediocre marker present
        mild = float(cfg.get("mediocre_mild_negative_score", -0.18))
        neu = float(cfg.get("mediocre_score", -0.12))
        # Contrastive follow-up in same clause (word-boundary — not "ama" inside "ortalama")
        contrast = bool(re.search(r"(?<![a-zçğıöşü])(ama|fakat|ancak)(?![a-zçğıöşü])", folded))
        contrast = contrast or _any_cue(low, folded, ["dusuk", "düşük", "kotu", "kötü", "berbat"])
        if aspect_key in ("food_taste", "meat_quality", "drink_quality", "room_size"):
            if contrast:
                sentiment, score = "Negative", mild
            else:
                sentiment, score = "Neutral", neu
        else:
            sentiment, score = "Neutral", neu
        notes.append("mediocre_lexicon")

    # Queue complaints are Negative (incl. şezlong sıra under pool_lounger)
    positive_wait_absence = any(
        w in folded for w in ("beklemiyor", "beklemeden", "beklemiyorsunuz")
    ) and not any(w in folded for w in ("alinamiyor", "alınamıyor", "imkansiz", "imkansız", "yok", "zor"))
    if not positive_wait_absence and (
        aspect_key in ("service_queue", "pool_queue", "pool_lounger") or frame in ("queue", "pool")
    ):
        if _any_cue(low, folded, cfg.get("queue_negative_cues") or []) or _any_cue(
            low, folded,
            ["bulunmuyor", "sezlong yok", "şezlong yok", "siraya", "sıraya", "lounger"],
        ):
            qscore = float(cfg.get("queue_negative_score", -0.55))
            if sentiment != "Positive" or aspect_key in ("service_queue", "pool_queue", "pool_lounger"):
                sentiment = "Negative"
                score = min(score if score < 0 else qscore, qscore)
                notes.append("queue_negative")
            elif sentiment == "Positive" and _any_cue(low, folded, ["alinamiyor", "alınamıyor", "bekleniyor", "uzun", "bulunmuyor"]):
                sentiment = "Negative"
                score = qscore
                notes.append("queue_negative")

    # Room noise / sound insulation
    if aspect_key == "room_noise" or _any_cue(low, folded, cfg.get("room_noise_negative_cues") or []):
        rscore = float(cfg.get("room_noise_negative_score", -0.5))
        sentiment = "Negative"
        score = min(score if score < 0 else rscore, rscore)
        notes.append("room_noise_negative")

    # Sarcasm: "500 metre yürümek… güzel" / "güzel bir yanı yok"
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []):
        sscore = float(cfg.get("sarcasm_negative_score", -0.55))
        sentiment = "Negative"
        score = min(score if score < 0 else sscore, sscore)
        notes.append("sarcasm_negative")

    # Disappointment booking: "7/24 bar var diye tuttuk"
    if _any_cue(low, folded, cfg.get("disappointment_negative_cues") or []):
        dscore = float(cfg.get("disappointment_negative_score", -0.5))
        sentiment = "Negative"
        score = min(score if score < 0 else dscore, dscore)
        notes.append("disappointment_negative")

    # Money waste sarcasm
    if aspect_key == "value_for_money" or _any_cue(low, folded, cfg.get("value_waste_cues") or []):
        vscore = float(cfg.get("value_waste_score", -0.6))
        sentiment = "Negative"
        score = min(score if score < 0 else vscore, vscore)
        notes.append("value_waste")

    # Staff language
    if aspect_key == "staff_behavior" or _any_cue(low, folded, cfg.get("staff_language_negative_cues") or []):
        if _any_cue(low, folded, cfg.get("staff_language_negative_cues") or []):
            lscore = float(cfg.get("staff_language_negative_score", -0.55))
            sentiment = "Negative"
            score = min(score if score < 0 else lscore, lscore)
            notes.append("staff_language_negative")

    # Drink variety / limited bar concept
    if aspect_key == "drink_variety" or _any_cue(low, folded, cfg.get("drink_variety_negative_cues") or []):
        if aspect_key in ("drink_variety", "drink_quality", "general", "guest_experience") or frame == "bar":
            dv = float(cfg.get("drink_variety_negative_score", -0.45))
            if sentiment != "Positive" or aspect_key == "drink_variety":
                sentiment = "Negative"
                score = min(score if score < 0 else dv, dv)
                notes.append("drink_variety_negative")

    # Capacity / all-inclusive chaos → Negative
    if aspect_key in ("capacity", "guest_experience") or frame == "capacity":
        if _any_cue(low, folded, ["yorucu", "yorgunluk", "karisik", "karışık", "kalabalik", "kalabalık"]):
            cscore = -0.5
            if sentiment != "Positive":
                sentiment = "Negative"
                score = min(score if score < 0 else cscore, cscore)
                notes.append("capacity_negative")

    # Room size complaints
    if aspect_key == "room_size":
        if _any_cue(low, folded, cfg.get("room_size_negative_cues") or []):
            rscore = float(cfg.get("room_size_negative_score", -0.45))
            sentiment = "Negative"
            score = min(score if score < 0 else rscore, rscore)
            notes.append("room_size_negative")

    # Table not cleaned / not wiped
    if aspect_key == "table_cleanliness" and _any_cue(
        low, folded,
        ["temizletemed", "temizlenmed", "temizlenmem", "kirli", "silinmedi", "silen yok", "masa kirli"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("table_dirty")

    # Suppress false-friend positives under mediocre/topic-only
    friends = cfg.get("positive_topic_false_friends") or []
    if sentiment == "Positive" and score <= 0.25:
        # bare "lezzet" without praise adverb
        if "lezzet" in folded and not _any_cue(low, folded, ["lezzetli", "harika", "mukemmel", "mükemmel", "enfes", "nefis"]):
            if _any_cue(low, folded, mediocre) or "ortalama" in folded:
                sentiment, score = "Neutral", float(cfg.get("mediocre_score", -0.12))
                notes.append("false_friend_lezzet")

    # Positive staff override — catch strong positive keywords when base is Neutral
    if sentiment == "Neutral" or (sentiment == "Positive" and score < 0.3):
        staff_pos = _any_cue(low, folded, [
            "guleryuzlu", "güleryüzlü", "guleryuz", "güleryüz",
            "yardimsever", "yardımsever", "yardimci", "yardımcı",
            "profesyonel", "ilgili", "ilgilendi", "kibar", "nazik",
            "samimi", "guler yuz", "güler yüz", "sicakkanli", "sıcakkanlı",
            "destek oldu", "cozdu", "çözdü", "halletti",
        ])
        if staff_pos and "değil" not in folded and "degil" not in folded:
            sentiment = "Positive"
            score = max(score, 0.65)
            notes.append("staff_positive")

    # WiFi / internet negative: yavas, kopuyor, baglanamiyor etc.
    if sentiment != "Negative" and aspect_key in ("wifi", "tech_general") and _any_cue(low, folded, [
        "yavas", "yavaş", "kopuyor", "kopuyodu", "kopuyordu",
        "baglanamiyor", "bağlanamıyor", "baglanmiyor", "bağlanmıyor",
        "kesiliyor", "kesilme", "cok kotu", "berbat",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.45, -0.45)
        notes.append("wifi_negative")

    # "dustu", "düştü" → Negative
    if sentiment != "Negative" and any(w in folded for w in ("dustu", "düştü", "dustu", "geriledi")):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.35, -0.35)
        notes.append("decline_negative")

    return sentiment, round(score, 2), notes


# ---------------------------------------------------------------------------
# Stage 5 — department anti-patterns
# ---------------------------------------------------------------------------
def apply_department_guards(
    mapping: dict[str, str],
    clause: str,
    aspect_key: str,
    cfg: Optional[dict] = None,
) -> tuple[dict[str, str], list[str]]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    notes: list[str] = []
    anti = cfg.get("anti_patterns") or {}
    out = dict(mapping)

    # Prefer pipeline aspect resolution department
    aspects = cfg.get("aspect_resolution") or {}
    # Alias normalization: sunbed wait must stay Havuz / Aktivite
    if aspect_key in ("pool_queue",) or (
        aspect_key == "service_queue" and _any_cue(low, folded, ["sezlong", "şezlong", "lounger"])
    ):
        aspect_key = "pool_lounger"
        notes.append("normalize_pool_lounger")
    if aspect_key in aspects:
        for k in ("department", "department_label", "aspect_key", "aspect_label", "category"):
            if aspects[aspect_key].get(k):
                out[k if k != "aspect_key" else "aspect_key"] = aspects[aspect_key][k]
                if k == "aspect_label":
                    out["aspect"] = aspects[aspect_key][k]
                if k == "department_label":
                    out["departmentLabel"] = aspects[aspect_key][k]
                if k == "department":
                    out["department"] = aspects[aspect_key][k]
                if k == "aspect_key":
                    out["aspect_key"] = aspects[aspect_key][k]

    # Finance anti-pattern
    fin = anti.get("finance") or {}
    dept_label = (out.get("department_label") or out.get("departmentLabel") or out.get("department") or "").lower()
    blocked_fin = [d.lower() for d in (fin.get("blocked_departments") or [])]
    if any(b in dept_label for b in blocked_fin) or dept_label in ("finans", "muhasebe"):
        if _any_cue(low, folded, fin.get("hard_block_cues") or []) or not _any_cue(
            low, folded, fin.get("required_cues") or []
        ):
            out["department"] = "genel"
            out["department_label"] = "Genel"
            out["departmentLabel"] = "Genel"
            out["aspect_key"] = out.get("aspect_key") or "value_for_money"
            notes.append("anti_finance")

    # Spa anti-pattern — never Spa for animation / F&B without wellness cues
    # BUT if pipeline already classified as spa (from spa_wellness frame), that's legitimate
    spa = anti.get("spa") or {}
    spa_blocked = any(b in dept_label for b in [d.lower() for d in (spa.get("blocked_departments") or [])])
    spa_blocked = spa_blocked or "spa" in dept_label
    has_spa_cues = _any_cue(low, folded, spa.get("required_cues") or [])
    # If pipeline resolved spa aspect_key, the clause has genuine spa content
    if aspect_key in ("spa", "spa_wellness"):
        has_spa_cues = True
    force_remap = aspect_key in (spa.get("force_remap_aspects") or [])
    if force_remap or (spa_blocked and not has_spa_cues):
        anim_cues = [
            "animasyon", "animator", "konser", "etkinlik", "show",
            "aktivite", "aktiviteler", "masa tenisi", "bayram nedeniyle",
        ]
        if aspect_key == "animation" or force_remap or _any_cue(low, folded, anim_cues):
            out["department"] = spa.get("remap_department") or "leisure"
            out["department_label"] = spa.get("remap_department_label") or "Rekreasyon & Eğlence"
            out["departmentLabel"] = out["department_label"]
            out["aspect_key"] = "animation"
            out["aspect_label"] = (aspects.get("animation") or {}).get("aspect_label", "Animasyon & Etkinlik")
            out["aspectLabel"] = out["aspect_label"]
            out["aspect"] = out["aspect_label"]
            out["category"] = (aspects.get("animation") or {}).get("category", "Rekreasyon & Eğlence")
            notes.append("anti_spa")
        elif aspect_key in ("cutlery", "table_cleanliness", "food_taste", "meat_quality", "drink_quality", "drink_variety"):
            out["department"] = "food_beverage"
            out["department_label"] = "Yiyecek & İçecek (F&B)"
            out["departmentLabel"] = "Yiyecek & İçecek (F&B)"
            notes.append("anti_spa")
        elif aspect_key in ("pool_lounger", "pool_queue") or (
            aspect_key == "service_queue" and _any_cue(low, folded, ["sezlong", "şezlong", "havuz"])
        ):
            out["department"] = "leisure"
            out["department_label"] = "Rekreasyon & Eğlence"
            out["departmentLabel"] = "Rekreasyon & Eğlence"
            if aspect_key == "pool_queue" or _any_cue(
                low, folded, ["sira", "sıra", "kuyruk", "bekle", "siraya", "sıraya"]
            ):
                out["aspect_key"] = "pool_queue"
                out["aspect_label"] = (aspects.get("pool_queue") or {}).get(
                    "aspect_label", "Servis / Kuyruk"
                )
            else:
                out["aspect_key"] = "pool_lounger"
                out["aspect_label"] = (aspects.get("pool_lounger") or {}).get(
                    "aspect_label", "Şezlong / Havuz Alanı"
                )
            out["aspectLabel"] = out["aspect_label"]
            out["aspect"] = out["aspect_label"]
            notes.append("anti_spa_pool_ok")
        elif aspect_key in ("guest_experience", "capacity", "value_for_money", "service_queue", "room_noise", "wifi"):
            if aspect_key == "room_noise":
                out["department"] = "housekeeping"
                out["department_label"] = "Kat Hizmetleri & Temizlik"
                out["departmentLabel"] = "Kat Hizmetleri & Temizlik"
            elif aspect_key == "wifi":
                out["department"] = "engineering"
                out["department_label"] = "Teknik Servis & IT"
                out["departmentLabel"] = "Teknik Servis & IT"
            elif aspect_key == "service_queue":
                out["department"] = "food_beverage"
                out["department_label"] = "Yiyecek & İçecek (F&B)"
                out["departmentLabel"] = "Yiyecek & İçecek (F&B)"
            else:
                out["department"] = "genel"
                out["department_label"] = "Genel"
                out["departmentLabel"] = "Genel"
            notes.append("anti_spa")

    # HK cleanliness incompatible with resolved aspects
    hk = anti.get("housekeeping_cleanliness") or {}
    if aspect_key in (hk.get("incompatible_aspects") or []):
        if "housekeeping" in dept_label or "kat" in dept_label or "temizlik" in (
            out.get("aspect_label") or out.get("aspectLabel") or ""
        ).lower():
            # Restore from aspect_resolution
            if aspect_key in aspects:
                out["department"] = aspects[aspect_key]["department"]
                out["department_label"] = aspects[aspect_key]["department_label"]
                out["departmentLabel"] = aspects[aspect_key]["department_label"]
                out["aspect_label"] = aspects[aspect_key]["aspect_label"]
                out["aspectLabel"] = aspects[aspect_key]["aspect_label"]
                out["aspect_key"] = aspects[aspect_key]["aspect_key"]
            notes.append("anti_hk_cleanliness")

    # Normalize aliases used by AbsaAspect
    if "department_label" in out and "departmentLabel" not in out:
        out["departmentLabel"] = out["department_label"]
    if "aspect_label" in out and "aspectLabel" not in out:
        out["aspectLabel"] = out["aspect_label"]

    return out, notes


# ---------------------------------------------------------------------------
# Stage 6 — severity
# ---------------------------------------------------------------------------
def resolve_severity(
    clause: str,
    sentiment: str,
    score: float,
    *,
    is_thanks: bool = False,
    is_meta: bool = False,
    frame: str = "",
    aspect_key: str = "",
    cfg: Optional[dict] = None,
) -> tuple[str, int]:
    cfg = cfg or load_pipeline_config()
    sev = cfg.get("severity") or {}
    low = clause.lower()
    folded = _fold(clause)
    words = len(clause.split())

    if is_meta:
        return "info", 1
    if is_thanks:
        return "info", 1
    if sentiment == "Positive":
        return ("info", 1) if score >= 0.55 else ("low", 2)
    if sentiment == "Neutral":
        if _any_cue(low, folded, sev.get("mild_cues") or []):
            return "low", 2
        return "medium", 2

    # Negative
    if _any_cue(low, folded, sev.get("critical_cues") or []):
        return "critical", 5
    # Long specific queue / capacity narratives outrank short fragments
    operational = frame in ("queue", "capacity") or aspect_key in ("service_queue", "capacity")
    if operational and words >= 18 and _any_cue(
        low, folded, ["kuyruk", "sira", "sıra", "bekle", "yorgun", "pes edip", "kalabal"]
    ):
        return "high", 4
    if _any_cue(low, folded, sev.get("high_cues") or []):
        return "high", 4
    if _any_cue(low, folded, sev.get("mild_cues") or []):
        return "medium", 3
    if score <= -0.75 and words > 6:
        return "high", 4
    if score <= -0.35:
        return "high", 4
    return "medium", 3


# ---------------------------------------------------------------------------
# Full clause classification
# ---------------------------------------------------------------------------
def classify_clause(
    clause: str,
    *,
    base_sentiment: Optional[str] = None,
    base_score: Optional[float] = None,
    base_mapping: Optional[dict] = None,
    cfg: Optional[dict] = None,
) -> ClauseDecision:
    cfg = cfg or load_pipeline_config()
    text = (clause or "").strip()
    if len(text) < 4:
        return ClauseDecision(clause=text, include=False, drop_reason="too_short")

    if is_meta_clause(text, cfg):
        return ClauseDecision(
            clause=text,
            include=False,
            drop_reason="meta",
            frame="meta",
            priority="info",
            priority_score=1,
            method="clause_pipeline_meta",
        )

    thanks = is_thanks_clause(text, cfg)
    scores = detect_frames(text, cfg)
    frame = primary_frame(scores)
    aspect = resolve_aspect(text, frame, scores, cfg)

    sentiment = base_sentiment or "Neutral"
    score = float(base_score if base_score is not None else 0.0)
    sentiment, score, sent_notes = apply_sentiment_modifiers(
        text, sentiment, score, frame, aspect["aspect_key"], cfg
    )

    mapping = {
        "department": aspect["department"],
        "department_label": aspect["department_label"],
        "departmentLabel": aspect["department_label"],
        "aspect_key": aspect["aspect_key"],
        "aspect_label": aspect["aspect_label"],
        "aspectLabel": aspect["aspect_label"],
        "aspect": aspect["aspect_label"],
        "category": aspect.get("category", "Genel"),
    }
    if base_mapping:
        # Keep ontology hints only when pipeline aspect is still general
        if aspect["aspect_key"] == "general":
            mapping = {**mapping, **{k: v for k, v in base_mapping.items() if v}}

    mapping, guard_notes = apply_department_guards(mapping, text, aspect["aspect_key"], cfg)

    if thanks:
        sentiment = "Positive" if sentiment == "Neutral" else sentiment
        if score == 0:
            score = 0.45

    priority, priority_score = resolve_severity(
        text,
        sentiment,
        score,
        is_thanks=thanks,
        is_meta=False,
        frame=frame,
        aspect_key=mapping.get("aspect_key", aspect["aspect_key"]),
        cfg=cfg,
    )

    return ClauseDecision(
        clause=text,
        include=True,
        frame=frame,
        aspect_key=mapping.get("aspect_key", aspect["aspect_key"]),
        aspect_label=mapping.get("aspect_label") or mapping.get("aspectLabel") or aspect["aspect_label"],
        department=mapping.get("department", aspect["department"]),
        department_label=mapping.get("department_label")
        or mapping.get("departmentLabel")
        or aspect["department_label"],
        category=mapping.get("category", aspect.get("category", "Genel")),
        sentiment=sentiment,
        sentiment_score=score,
        priority=priority,
        priority_score=priority_score,
        confidence=0.88 if aspect["aspect_key"] != "general" else 0.7,
        method="clause_pipeline",
        frame_scores=scores,
        overrides=sent_notes + guard_notes + (["thanks"] if thanks else []),
    )


def classify_clauses(
    clauses: list[str],
    *,
    full_text: str = "",
    sentiment_fn=None,
    mapping_fn=None,
) -> list[ClauseDecision]:
    """Run stages 2–6 over segmented clauses."""
    cfg = load_pipeline_config()
    out: list[ClauseDecision] = []
    for clause in clauses:
        base_sent, base_score = None, None
        base_map = None
        if sentiment_fn:
            try:
                base_sent, base_score = sentiment_fn(clause)
            except Exception:
                logger.warning("Sentiment function failed in pipeline", exc_info=True)
        if mapping_fn:
            try:
                base_map = mapping_fn(full_text or clause, clause)
            except Exception:
                logger.warning("Mapping function failed in pipeline", exc_info=True)
        decision = classify_clause(
            clause,
            base_sentiment=base_sent,
            base_score=base_score,
            base_mapping=base_map,
            cfg=cfg,
        )
        out.append(decision)
    return out


# ---------------------------------------------------------------------------
# Stage 7 — summary
# ---------------------------------------------------------------------------
def _build_multi_theme_summary(
    ops: list[ClauseDecision],
    summary_cfg: dict,
    max_words: int,
) -> Optional[str]:
    """Compose multi-issue operational summary for long mixed-complaint reviews."""
    min_ops = int(summary_cfg.get("multi_theme_min_ops", 5))
    max_themes = int(summary_cfg.get("multi_theme_max", 4))
    theme_phrases: dict = summary_cfg.get("theme_phrases") or {}
    if len(ops) < min_ops or not theme_phrases:
        return None

    aspect_order = summary_cfg.get("theme_aspect_order") or list(theme_phrases.keys())
    seen: set[str] = set()
    parts: list[str] = []
    for key in aspect_order:
        if key in seen:
            continue
        if not any(d.aspect_key == key for d in ops):
            continue
        phrase = theme_phrases.get(key)
        if phrase:
            parts.append(phrase)
            seen.add(key)
        if len(parts) >= max_themes:
            break

    if len(parts) < 2:
        return None

    combined = "; ".join(parts)
    words = combined.split()
    if len(words) > max_words:
        combined = " ".join(words[:max_words]).rstrip(",;:") + "..."
    elif not combined.endswith((".", "…", "...")):
        combined = combined + "."
    return combined


def build_operational_summary(
    text: str,
    decisions: Optional[list[ClauseDecision]] = None,
    cfg: Optional[dict] = None,
) -> str:
    """Summary from top operational complaints — not first narrative sentence."""
    cfg = cfg or load_pipeline_config()
    summary_cfg = cfg.get("summary") or {}
    max_words = int(summary_cfg.get("max_words", 28))
    prefer = summary_cfg.get("prefer_cues") or []
    avoid = summary_cfg.get("avoid_openers") or []

    if decisions is None:
        from app.services.absa_service import split_clauses_absa

        decisions = classify_clauses(split_clauses_absa(text) or [text], full_text=text)

    ops = [
        d for d in decisions
        if d.include and d.sentiment in ("Negative", "Neutral") and d.priority != "info"
    ]
    length_weight = float(summary_cfg.get("length_weight", 0.35))
    length_cap = float(summary_cfg.get("length_cap", 4.0))
    specificity = summary_cfg.get("specificity_cues") or []

    def rank(d: ClauseDecision) -> float:
        folded = _fold(d.clause)
        words = len(d.clause.split())
        bonus = sum(1.5 for c in prefer if _fold(c) in folded)
        spec = sum(1.0 for c in specificity if _fold(c) in folded)
        sev = float(d.priority_score)
        sent = abs(float(d.sentiment_score))
        # severity × length/specificity — main queue paragraph beats short fragments
        length_factor = 1.0 + length_weight * min(words / 10.0, length_cap)
        queue_boost = 2.0 if d.frame == "queue" or d.aspect_key == "service_queue" else 0.0
        if d.aspect_key == "service_queue":
            queue_boost += 4.0
        if d.frame == "capacity" or d.aspect_key == "capacity":
            queue_boost = max(queue_boost, 1.5)
        prefer_aspects = summary_cfg.get("prefer_aspects") or []
        if d.aspect_key in prefer_aspects:
            queue_boost += 1.0
        # Pool lounger is secondary when F&B queue themes dominate the review
        if d.aspect_key == "pool_lounger":
            queue_boost -= 1.5
        return (sev * 2.0 + sent + bonus + spec + queue_boost) * length_factor

    ops.sort(key=rank, reverse=True)

    composite = _build_multi_theme_summary(ops, summary_cfg, max_words)
    if composite:
        return composite

    if ops:
        best = ops[0].clause.strip()
        # Prefer F&B queue / capacity clauses — not generic long pool clauses
        for d in ops[:6]:
            f = _fold(d.clause)
            if not any(_fold(c) in f for c in prefer):
                continue
            if d.frame in ("queue", "capacity") or d.aspect_key in (
                "service_queue", "capacity", "drink_variety",
            ):
                best = d.clause.strip()
                break
    else:
        # Fallback: scan full text for prefer cues
        raw = re.sub(r"\s+", " ", (text or "").strip())
        sentences = [s.strip() for s in re.split(r"[.!?]+", raw) if s.strip()]
        scored: list[tuple[float, str]] = []
        for s in sentences:
            low = s.lower()
            folded = _fold(s)
            if any(a.lower() in low or _fold(a) in folded for a in avoid):
                continue
            sc = sum(1.0 for c in prefer if c.lower() in low or _fold(c) in folded)
            scored.append((sc, s))
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1] if scored and scored[0][0] > 0 else (sentences[0] if sentences else raw)

    # Strip avoided openers (may be stacked: tek kelimeyle + özetleyecek olsaydım)
    for _ in range(4):
        low_best = best.lower()
        stripped = False
        for a in avoid:
            al = a.lower()
            if low_best.startswith(al):
                best = best[len(a):].lstrip(" ,.-")
                stripped = True
                break
            # opener may sit after a short leftover fragment
            idx = low_best.find(al)
            if 0 <= idx <= 12:
                best = (best[:idx] + best[idx + len(a):]).lstrip(" ,.-")
                stripped = True
                break
        if not stripped:
            break

    # Prefer cue-centered window ONLY for long clauses; short ops clauses stay intact
    words = best.split()
    no_crop = int(summary_cfg.get("no_crop_below_words", max_words))
    if len(words) <= no_crop and len(words) <= max_words:
        if best and not best.endswith((".", "…", "...")):
            best = best + "."
        return best

    prefer_idx = next(
        (i for i, w in enumerate(words) if any(_fold(c) in _fold(w) for c in prefer)),
        0,
    )
    # Prefer full drink-queue clauses over mid-crop starting at "sıra"
    if prefer_idx > 0 and any(_fold(w) in ("icecek", "içecek", "bar", "dakika") for w in words[:prefer_idx + 1]):
        prefer_idx = 0
    if prefer_idx > 0 and len(words) > max_words:
        # Keep a little left context but drop pure meta openers
        start = max(0, prefer_idx - 1)
        left = _fold(words[start]) if start < prefer_idx else ""
        if left in ("sadece", "diyebilirdim", "olsaydim", "ozetleyecek", "tek", "herhangi", "bir"):
            start = prefer_idx
        if start > 0 and any(_fold(w) in ("dakika", "dk", "kisi", "kişilik", "kisilik") for w in words[start:start + 2]):
            start = 0
        words = words[start:]
        best = " ".join(words)

    words = best.split()
    if len(words) > max_words:
        idx = next(
            (i for i, w in enumerate(words) if any(_fold(c) in _fold(w) for c in prefer)),
            0,
        )
        start = max(0, idx - 1) if idx > 2 else 0
        words = words[start:start + max_words]
        best = " ".join(words).rstrip(",;:") + "..."
    elif best and not best.endswith((".", "…", "...")):
        best = best + "."
    return best


class ClausePipeline:
    """Facade used by AbsaService / RagService."""

    @staticmethod
    def reload() -> None:
        reload_pipeline_config()

    @staticmethod
    def should_drop(clause: str) -> bool:
        return is_meta_clause(clause)

    @staticmethod
    def refine(
        clause: str,
        *,
        sentiment: str,
        score: float,
        mapping: Optional[dict] = None,
    ) -> ClauseDecision:
        return classify_clause(
            clause,
            base_sentiment=sentiment,
            base_score=score,
            base_mapping=mapping,
        )

    @staticmethod
    def process(
        clauses: list[str],
        full_text: str = "",
        sentiment_fn=None,
        mapping_fn=None,
    ) -> list[ClauseDecision]:
        return classify_clauses(
            clauses,
            full_text=full_text,
            sentiment_fn=sentiment_fn,
            mapping_fn=mapping_fn,
        )

    @staticmethod
    def summary(text: str, decisions: Optional[list[ClauseDecision]] = None) -> str:
        return build_operational_summary(text, decisions=decisions)
