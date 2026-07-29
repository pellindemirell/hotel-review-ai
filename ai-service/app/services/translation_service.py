import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from langdetect import detect
from deep_translator import GoogleTranslator

logger = logging.getLogger("ai_service")
_TRANSLATE_TIMEOUT_SEC = 3  # UI yolunu Google ile bloke etmesin
_translate_pool = ThreadPoolExecutor(max_workers=10)
_TR_CHAR_RE = None
_TRANSLATE_CACHE = {}

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
            return _TRANSLATE_CACHE[s_text]

        # 1. Dil Tespiti — TR karakterleri veya yaygın Türkçe kelimeler varsa atla
        detected_lang = source_lang
        if not detected_lang:
            if _has_turkish_chars(s_text) or any(w in s_text.lower().split() for w in ("ve", "bir", "otel", "oda", "cok", "çok", "ile", "da", "de", "iyi", "kötü", "güzel", "harika", "yemek", "personel", "gibi", "her", "biz", "ama", "fakat", "en", "enle", "ben", "sen", "var", "yok", "da", "de", "ise")):
                detected_lang = "tr"
            else:
                try:
                    detected_lang = detect(s_text)
                except Exception:
                    detected_lang = "tr"

        # 2. Türkçe ise Çevirme
        if not detected_lang or detected_lang.lower() in ('tr', 'az', 'unknown'):
            _TRANSLATE_CACHE[s_text] = (s_text, 'tr')
            return s_text, 'tr'

        # 2b. Bilinen kalıplar için çevrimdışı sözlük (ağ gerekmez)
        from app.services.turkish_nlp_utils import apply_offline_translation
        offline = apply_offline_translation(s_text)
        if offline != s_text:
            _TRANSLATE_CACHE[s_text] = (offline, detected_lang)
            return offline, detected_lang

        # 3. Yabancı Dil Çeviri İşlemi
        try:
            future = _translate_pool.submit(
                GoogleTranslator(source='auto', target='tr').translate, s_text,
            )
            translated = future.result(timeout=_TRANSLATE_TIMEOUT_SEC)
            if translated and len(translated) > 2:
                _TRANSLATE_CACHE[s_text] = (translated, detected_lang)
                return translated, detected_lang
        except FuturesTimeoutError:
            pass
        except Exception as e:
            pass

        fallback = apply_offline_translation(s_text)
        _TRANSLATE_CACHE[s_text] = (fallback, detected_lang)
        return fallback, detected_lang
