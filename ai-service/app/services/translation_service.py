import logging
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from langdetect import detect, DetectorFactory
from deep_translator import GoogleTranslator

logger = logging.getLogger("ai_service")
# langdetect varsayılan olarak deterministik değil; aynı metin farklı çağrılarda
# farklı dil dönebiliyordu.
DetectorFactory.seed = 0

_TRANSLATE_TIMEOUT_SEC = float(os.getenv("TRANSLATE_TIMEOUT_SEC", "8"))
_translate_pool = ThreadPoolExecutor(max_workers=10)
_TR_CHAR_RE = None

# Sınırlı cache: önceden sınırsız bir dict'ti ve uzun süren serviste tüm yorum
# metinlerini bellekte biriktiriyordu.
_TRANSLATE_CACHE_MAX = int(os.getenv("TRANSLATE_CACHE_MAX", "5000"))
_TRANSLATE_CACHE: "OrderedDict[str, tuple[str, str]]" = OrderedDict()


def _cache_put(key: str, value: tuple[str, str]) -> None:
    _TRANSLATE_CACHE[key] = value
    _TRANSLATE_CACHE.move_to_end(key)
    while len(_TRANSLATE_CACHE) > _TRANSLATE_CACHE_MAX:
        _TRANSLATE_CACHE.popitem(last=False)

def _has_turkish_chars(text: str) -> bool:
    global _TR_CHAR_RE
    if _TR_CHAR_RE is None:
        import re
        _TR_CHAR_RE = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
    return bool(_TR_CHAR_RE.search(text))

class TranslationService:
    @staticmethod
    def translate_to_turkish(text: str, source_lang: str = None) -> tuple[str, str]:
        """
        Yorumun dilini tespit eder ve Türkçe değilse çevirir.
        Geri dönüş değeri: (çevrilmiş_metin, tespit_edilen_dil)
        """
        if not text or not text.strip():
            return "", "unknown"

        s_text = text.strip()
        if s_text in _TRANSLATE_CACHE:
            _TRANSLATE_CACHE.move_to_end(s_text)
            return _TRANSLATE_CACHE[s_text]

        # 1. Dil Tespiti
        # Önceden: source_lang verilmişse tespit TAMAMEN atlanıyordu. Çağıranlar
        # (ör. .NET içe aktarma) dili bilmediğinde varsayılan "tr" gönderdiği için
        # İngilizce yorumlar Türkçe sayılıp hiç çevrilmiyor, Türkçe sözlükle
        # eşleşmedikleri için de %95'i "Nötr / 0.0" skor alıyordu.
        # Artık langdetect birincil kaynak; source_lang yalnızca tespit
        # başarısız olduğunda ipucu olarak kullanılıyor.
        detected_lang = None
        try:
            detected_lang = detect(s_text)
        except Exception:
            detected_lang = None

        if not detected_lang:
            declared = (source_lang or "").strip().lower()
            if declared:
                detected_lang = declared
            elif _has_turkish_chars(s_text) or any(
                w in s_text.lower().split()
                for w in ("ve", "bir", "otel", "oda", "çok", "ile", "iyi",
                          "kötü", "güzel", "harika", "yemek", "personel")
            ):
                # NOT: Bu sezgisel yol yalnızca langdetect başarısız olduğunda devreye girer.
                # Tek başına güvenilmez: İngilizce metinlerdeki Türkçe özel isimler
                # ("Ms. Tülay") Türkçe karakter içerdiği için yanlış pozitif üretiyor.
                detected_lang = "tr"
            else:
                detected_lang = "tr"

        # 2. Türkçe ise Çevirme
        if not detected_lang or detected_lang.lower() in ('tr', 'az', 'unknown'):
            _cache_put(s_text, (s_text, 'tr'))
            return s_text, 'tr'

        # 2b. Bilinen kalıplar için çevrimdışı sözlük (ağ gerekmez)
        from app.services.turkish_nlp_utils import apply_offline_translation
        offline = apply_offline_translation(s_text)
        if offline != s_text:
            _cache_put(s_text, (offline, detected_lang))
            return offline, detected_lang

        # 3. Yabancı Dil Çeviri İşlemi
        try:
            future = _translate_pool.submit(
                GoogleTranslator(source='auto', target='tr').translate, s_text,
            )
            translated = future.result(timeout=_TRANSLATE_TIMEOUT_SEC)
            if translated and len(translated) > 2:
                _cache_put(s_text, (translated, detected_lang))
                return translated, detected_lang
        except FuturesTimeoutError:
            # Sessizce yutulduğunda "neden sonuçlar kötü" sorusu loglardan cevaplanamıyordu.
            logger.warning(
                "Çeviri zaman aşımına uğradı (%.1f sn, dil=%s). Metin çevrilmeden işlenecek.",
                _TRANSLATE_TIMEOUT_SEC, detected_lang,
            )
        except Exception as e:
            logger.warning("Çeviri başarısız (dil=%s): %s", detected_lang, e)

        fallback = apply_offline_translation(s_text)
        _cache_put(s_text, (fallback, detected_lang))
        return fallback, detected_lang
