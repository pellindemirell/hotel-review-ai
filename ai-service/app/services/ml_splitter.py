"""
Machine Learning Clause Splitter Service
Uses the trained Logistic Regression model and vectorizers to split Turkish text into clauses.
Falls back to original rule-based splitter if models are missing or if any error occurs.
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional, List
import joblib
from scipy.sparse import hstack, csr_matrix
from app.services.turkish_nlp_utils import COORDINATION_ADJECTIVES

logger = logging.getLogger(__name__)

# Search paths for model files
_CANDIDATE_DIRS = [
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "simulation")),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "simulation")),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulation")),
    os.path.normpath(os.path.join(os.getcwd(), "simulation")),
    r"D:\KodYazılımStaj1\simulation",
]

_clf = None
_vec_token = None
_vec_left = None
_vec_right = None
_loaded = False

def _load_model() -> bool:
    global _clf, _vec_token, _vec_left, _vec_right, _loaded
    if _loaded:
        return _clf is not None

    model_dir = None
    for d in _CANDIDATE_DIRS:
        if os.path.isdir(d):
            model_dir = d
            break

    if not model_dir:
        logger.debug("ML Splitter: Simulation directory not found in candidate paths. Using rule-based splitter.")
        _loaded = True
        return False

    model_path = os.path.join(model_dir, "clause_split_model.joblib")
    vec_path = os.path.join(model_dir, "clause_split_vectorizers.joblib")

    if not os.path.isfile(model_path) or not os.path.isfile(vec_path):
        logger.debug("ML Splitter: Model files not found in %s. Using rule-based splitter.", model_dir)
        _loaded = True
        return False

    try:
        _clf = joblib.load(model_path)
        vecs = joblib.load(vec_path)
        _vec_token = vecs['token']
        _vec_left = vecs['left']
        _vec_right = vecs['right']
        logger.info("ML Splitter: Successfully loaded clause split model and vectorizers from %s", model_dir)
    except Exception as e:
        logger.warning("ML Splitter: Error loading models: %s", e)
        _clf = None

    _loaded = True
    return _clf is not None


# Features matching training
VERB_SUFFIX_RE = re.compile(
    r'(du|dü|di|dı|tu|tü|ti|tı|muş|müş|miş|mış|se|sa|ecek|acak|uyor|üyor|iyor|ıyor|meli|malı|er|ar|ır|ir|ur|ür|r|nız|niz|nuz|nüz|ız|iz|uz|üz|im|ım|um|üm|sin|siniz|sun|sunuz|ler|lar|ydik|ydık|ydük|ydi|ydı|yordu|yördü|yorduk|yim|yım|dik|dık|duk|dük|tik|tık|tuk|tük)$',
    re.IGNORECASE
)

def _normalize_turkish(text: str) -> str:
    # Map Turkish specific characters to English/ASCII equivalents
    translation_table = str.maketrans(
        "ıİiIçÇğĞöÖşŞüÜ",
        "iiiiccggoossuu"
    )
    return text.translate(translation_table).lower()

NOMINAL_PREDS = {
    "temiz", "kirli", "pis", "eski", "yeni", "güzel", "harika", "mükemmel", "iyi", "kötü",
    "yeterli", "yetersiz", "lezzetli", "lezzetsiz", "taze", "bayat", "uzak", "yakın", "var", "yok",
    "mevcut", "memnun", "ilgili", "alakalı", "yardımsever", "kibar", "saygılı", "yüzlü", "yüzlüydü",
    "sakin", "huzurlu", "kalabalık", "gürültülü", "pahalı", "ucuz", "rahat", "konforlu", "geniş",
    "ferah", "büyük", "küçük", "sıcak", "soğuk", "yavaş", "hızlı", "dostu", "hazır", "hazırdı",
    "berbat", "başarısız", "başarılı", "organize", "hoş", "keyifli", "uygun", "zor", "kolay",
    "uzun", "kısa", "dolu", "boş", "eksik", "fazla", "az", "yüzeysel", "bakımlı", "bakımsız",
    "kaba", "tembel", "saygısız", "terbiyesiz", "görgüsüz", "cömert", "modern", "şık", "güvenli", "güvensiz",
    "müthiş", "enfes", "şahane", "olağanüstü", "harikulade"
}

NORMALIZED_NOMINAL_PREDS = {_normalize_turkish(np) for np in NOMINAL_PREDS}

DEPT_KEYWORDS = {
    "Oda Hizmetleri & Housekeeping": ["oda", "temiz", "yatak", "banyo", "havlu", "buklet", "balkon", "manzara", "minibar", "oda servis", "kat hizmet", "room", "bed", "bathroom", "clean", "towel", "pillow", "comfortable", "shower", "bedroom"],
    "Yiyecek & İçecek (F&B)": ["yemek", "kahvaltı", "restoran", "bar", "minibar", "yiyecek", "içecek", "lezzet", "menü", "büfe", "akşam", "öğle", "mutfak", "çatal", "bıçak", "tabak", "servis", "garson", "food", "breakfast", "dinner", "lunch", "menu", "drink", "meal", "taste", "delicious", "buffet", "restaurant", "wine", "beer", "dondurma", "pizza", "kumpir", "gözleme"],
    "Ön Büro & Misafir İlişkileri": ["resepsiyon", "check-in", "checkin", "giriş", "çıkış", "karşılama", "rezervasyon", "misafir ilişki", "reception", "check out", "checkout", "booking", "front desk", "invoice", "payment"],
    "Teknik Servis & IT": ["klima", "wifi", "televizyon", "tv", "elektrik", "arıza", "bozuk", "çalışmıyor", "teknik", "internet", "kumanda", "çekmiyor", "kopuyor", "bağlantı", "air conditioner", "heating", "water pressure", "elevator", "remote", "channel", "wi-fi"],
    "Rekreasyon & Eğlence": ["havuz", "spa", "animasyon", "plaj", "eğlence", "aktivite", "aqua", "aquapark", "sauna", "hamam", "fitness", "çocuk", "şezlong", "şemsiye", "pool", "beach", "entertainment", "activity", "kids club", "kidsclub", "sunbed", "lounger", "performance", "show", "dance", "kaydırak", "kaydirak"],
    "Çevre, Güvenlik & Ulaşım": ["otopark", "park", "konum", "çevre", "güvenlik", "transfer", "ulaşım", "bahçe", "manzara", "deniz", "plaj", "location", "parking", "transport", "security", "garden", "distance", "walk", "station", "airport", "bus", "metro", "taxi"],
    "Otel Atmosferi & Misafir Profili": ["atmosfer", "ortam", "aile", "sakin", "huzurlu", "kalabalık", "gürültü", "dekorasyon", "fiyat", "performans", "tavsiye", "genel", "otelin", "atmosphere", "quiet", "noise", "price", "value", "overall", "recommend", "experience", "decoration", "family"],
    "Personel Davranışı": ["personel", "çalışan", "görevli", "servis", "güleryüz", "ilgili", "yardımsever", "kibar", "profesyonel", "teşekkür", "ilgi", "staff", "friendly", "helpful", "service", "manager", "receptionist", "waiter", "polite", "professional", "thank"],
}

CANDIDATES = [
    r'\.', r'\!', r'\?', r'\,', r'\;', r'\:',
    r'\bve\b', r'\bveya\b', r'\bama\b', r'\bfakat\b', r'\bancak\b', r'\blakin\b',
    r'\brağmen\b', r'\bragmen\b',
    r'\bçünkü\b', r'\bcunku\b', r'\bayrıca\b', r'\bayrica\b', r'\bhatta\b',
    r'\bböylece\b', r'\bboylece\b', r'\byani\b', r'\bözellikle\b', r'\bozellikle\b',
    r'\büstelik\b', r'\bustelik\b', r'\bbir de\b', r'\bbirde\b', r'\byanı sıra\b',
    r'\byani sira\b', r'\bgerek\b', r'\bister\b', r'\bnitekim\b', r'\bzaten\b',
    r'\bbunun yanında\b', r'\bbunun yaninda\b', r'\bhem\b', r'\bya da\b', r'\byada\b'
]
CANDIDATE_PATTERN = re.compile('|'.join(CANDIDATES), re.IGNORECASE)

def _get_dept_mention(text: str) -> Optional[str]:
    text_low = text.lower()
    for dept, kws in DEPT_KEYWORDS.items():
        if any(kw in text_low for kw in kws):
            return dept
    return None

def _has_verb(text: str) -> bool:
    words = [w.strip() for w in re.split(r'\W+', text) if w.strip()]
    if not words:
        return False
    for w in words[-2:]:
        if VERB_SUFFIX_RE.search(w):
            return True
        w_norm = _normalize_turkish(w)
        if w_norm in NORMALIZED_NOMINAL_PREDS:
            return True
        for np_norm in NORMALIZED_NOMINAL_PREDS:
            if len(np_norm) >= 3 and w_norm.startswith(np_norm):
                rem = w_norm[len(np_norm):]
                if not rem or rem[0] in 'dylsmnrt':
                    return True
    return False

def _has_verb_any(text: str) -> bool:
    words = [w.strip() for w in re.split(r'\W+', text) if w.strip()]
    for w in words:
        if VERB_SUFFIX_RE.search(w):
            return True
        w_norm = _normalize_turkish(w)
        if w_norm in NORMALIZED_NOMINAL_PREDS:
            return True
        for np_norm in NORMALIZED_NOMINAL_PREDS:
            if len(np_norm) >= 3 and w_norm.startswith(np_norm):
                rem = w_norm[len(np_norm):]
                if not rem or rem[0] in 'dylsmnrt':
                    return True
    return False

def split_clauses_ml(text: str) -> Optional[List[str]]:
    """
    Splits text into clauses using the ML model.
    Returns None if the model is not loaded or fails, signaling the caller to fallback to rule-based.
    """
    if not _load_model():
        return None

    try:
        text_clean = re.sub(r"\s+", " ", text.strip())
        if len(text_clean) < 15:
            return [text_clean] if text_clean else []

        # Protect decimals/dates/times and Turkish ordinals (e.g. "2. hafta")
        text_protected = re.sub(r"(\d+)\.(\d+)", r"\1__DOT__\2", text_clean)
        text_protected = re.sub(r"(\d+)\.(\s)", r"\1__DOT__\2", text_protected)
        text_protected = re.sub(r"(\d+),(\d+)", r"\1__COMMA__\2", text_protected)

        candidates = list(CANDIDATE_PATTERN.finditer(text_protected))
        if not candidates:
            return [text_clean]

        tokens_list = []
        left_list = []
        right_list = []
        struct_feats = []

        for m in candidates:
            cand_token = m.group().lower().strip()
            cand_start = m.start()
            cand_end = m.end()

            left_context = text_protected[max(0, cand_start - 60):cand_start]
            right_context = text_protected[cand_end:min(len(text_protected), cand_end + 60)]

            left_dept = _get_dept_mention(left_context)
            right_dept = _get_dept_mention(right_context)
            dept_shift = int(left_dept is not None and right_dept is not None and left_dept != right_dept)

            left_has_verb = int(_has_verb(left_context))
            right_has_verb = int(_has_verb(right_context))

            tokens_list.append(cand_token)
            left_list.append(left_context)
            right_list.append(right_context)
            struct_feats.append([
                dept_shift,
                left_has_verb,
                right_has_verb,
                len(left_context.strip()),
                len(right_context.strip())
            ])

        # Vectorize features
        X_token = _vec_token.transform(tokens_list)
        X_left = _vec_left.transform(left_list)
        X_right = _vec_right.transform(right_list)
        X_structural = csr_matrix(struct_feats)

        X_all = hstack([X_token, X_left, X_right, X_structural])
        
        # Predict using probabilities and 0.35 threshold (optimized for Random Forest)
        probs = _clf.predict_proba(X_all)[:, 1]
        predictions = (probs >= 0.35).astype(int)

        # Split text at predicted boundaries (with linguistic overrides)
        split_indices = []
        for m, pred, tokens, left_ctx, right_ctx in zip(candidates, predictions, tokens_list, left_list, right_list):
            # Override 1: Hard punctuation boundaries should always split
            if tokens in ('.', '!', '?'):
                pred = 1
            # Override 2: Contrastive/causal conjunctions connecting two clauses with verbs should split
            elif tokens in ('ama', 'fakat', 'ancak', 'lakin', 'çünkü', 'cunku', 'rağmen', 'ragmen') and _has_verb_any(left_ctx) and _has_verb_any(right_ctx):
                pred = 1
                # Check if followed by only 1 word before a sentence boundary
                boundary_match = re.search(r'[.!?:]', right_ctx)
                if boundary_match:
                    pre_boundary_text = right_ctx[:boundary_match.start()]
                    words_before_boundary = [w.strip() for w in re.split(r'\W+', pre_boundary_text) if w.strip()]
                    if len(words_before_boundary) <= 1:
                        pred = 0
                # "X değil ama Y iyi" style should still split; avoid folding with previous praise.
                if re.search(r'\b(degil|değil|yok)\b', left_ctx, re.IGNORECASE) and re.search(
                    r'\b(iyi|guzel|güzel|harika|mukemmel|mükemmel)\b', right_ctx, re.IGNORECASE
                ):
                    pred = 1
            # Override 2b: contrastive split even with lighter verb evidence when dept shifts
            elif tokens in ('ama', 'fakat', 'ancak', 'lakin', 'rağmen', 'ragmen') and dept_shift:
                pred = 1
            # Override 3: 've' connecting genitive/plural noun lists should never split
            elif tokens == 've' and re.search(r'(?:nin|nin|larin|lerin|inin|inin|unun|unun|nin|nin|in|ın|un|ün|nin|nın|nun|nün)\s*$', left_ctx.strip(), re.IGNORECASE):
                pred = 0
            # Override 3b: 've' connecting adjectives (e.g. "dalgali ve bulanik") should never split
            elif tokens == 've':
                right_clean = right_ctx.strip().split()
                if right_clean and right_clean[0] in COORDINATION_ADJECTIVES:
                    pred = 0
                else:
                    joined_lr = (left_ctx + " " + right_ctx).lower()
                    proximity = any(w in joined_lr for w in ("yakin", "yakın", "uzak", "mesafe", "yakind"))
                    if proximity:
                        pred = 0
                    elif dept_shift and _has_verb_any(left_ctx) and _has_verb_any(right_ctx):
                        # Cross-department "ve" with verbs on both sides → force split
                        pred = 1
                    elif _has_verb_any(left_ctx) and _has_verb_any(right_ctx):
                        if dept_shift and (len(left_ctx.strip()) >= 12 and len(right_ctx.strip()) >= 12):
                            pred = 1
                        else:
                            pred = 0
                    else:
                        pred = 0
            # Override 4: conservative split on comma/semicolon to reduce false splits in long narratives
            elif tokens in (',', ';') and _has_verb_any(left_ctx) and _has_verb_any(right_ctx):
                if tokens == ';':
                    pred = 1
                else:
                    # Comma split when domain/topic shift is explicit (or both sides are long predicates).
                    pred = 1 if dept_shift or (len(left_ctx.strip()) >= 24 and len(right_ctx.strip()) >= 24) else 0

            if pred == 1:
                if re.match(r'^\w', tokens):
                    split_indices.append(m.start())
                else:
                    split_indices.append(m.end())

        # Deduplicate and sort split indices (merge splits within 3 characters of each other)
        unique_indices = []
        for idx in sorted(split_indices):
            if not unique_indices or idx - unique_indices[-1] > 3:
                unique_indices.append(idx)
        split_indices = unique_indices

        clauses = []
        prev_idx = 0
        for idx in split_indices:
            clause = text_protected[prev_idx:idx].strip()
            # Clean trailing/leading punctuation
            clause = re.sub(r'^[.,!?;:\s]+|[.,!?;:\s]+$', '', clause).strip()
            # Restore protected characters
            clause = clause.replace("__DOT__", ".").replace("__COMMA__", ",")
            # Ensure the clause contains at least one letter or digit
            if len(clause) >= 4 and re.search(r'[a-zA-Z0-9ıüğşöçİÜĞŞÖÇâîûÂÎÛ]', clause):
                clauses.append(clause)
            prev_idx = idx

        rest = text_protected[prev_idx:].strip()
        rest = re.sub(r'^[.,!?;:\s]+|[.,!?;:\s]+$', '', rest).strip()
        rest = rest.replace("__DOT__", ".").replace("__COMMA__", ",")
        if len(rest) >= 4 and re.search(r'[a-zA-Z0-9ıüğşöçİÜĞŞÖÇâîûÂÎÛ]', rest):
            clauses.append(rest)

        # Fallback if splitting left nothing
        if not clauses and text_clean:
            return [text_clean]

        return clauses
    except Exception as e:
        logger.warning("ML Splitter: Error during inference: %s", e)
        return None
