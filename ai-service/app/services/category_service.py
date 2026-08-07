import os
import joblib
import logging
import string
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from typing import List, Dict, Tuple, Optional

from app.services.category_rules import (
    classify_by_rules,
    rules_win_over_model,
    MODEL_CONFIDENCE_MIN,
    RULE_CONFIDENCE_WIN,
    CONFIDENCE_FALLBACK_MIN,
    RuleClassificationResult,
)
from app.services.turkish_nlp_utils import (
    ALL_CATEGORIES,
    CAT_OTHER,
    canonical_category,
    normalize_turkish,
)

logger = logging.getLogger("ai_service")

# Model dizini: önce MODEL_DIR ortam değişkeni, sonra repo-göreli `simulation/`.
# Önceden tek bir Windows mutlak yolu ("D:\\KodYazılımStaj1\\simulation") gömülüydü;
# başka hiçbir işletim sisteminde bulunamıyor, model sessizce yüklenmiyordu.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_MODEL_DIRS = [
    os.environ.get("MODEL_DIR"),
    os.path.normpath(os.path.join(_HERE, "..", "..", "simulation")),
    os.path.normpath(os.path.join(_HERE, "..", "..", "..", "simulation")),
    os.path.normpath(os.path.join(os.getcwd(), "simulation")),
]


def _resolve_model_dir() -> str:
    for candidate in _CANDIDATE_MODEL_DIRS:
        if candidate and os.path.isfile(os.path.join(candidate, "category_model.joblib")):
            return candidate
    # Bulunamazsa ilk geçerli adayı döndür; load_model() zaten var-mı kontrolü yapıyor.
    return next((c for c in _CANDIDATE_MODEL_DIRS if c), _HERE)


MODEL_DIR = _resolve_model_dir()
MODEL_PATH = os.path.join(MODEL_DIR, "category_model.joblib")
VECTORIZER_PATH = os.path.join(MODEL_DIR, "vectorizer.joblib")
CSV_PATH = os.path.join(MODEL_DIR, "synthetic_reviews.csv")


class CategoryService:
    def __init__(self):
        self.model = None
        self.vectorizer = None
        self.last_method: str = "fallback"
        self.load_model()

    def load_model(self):
        if os.path.exists(MODEL_PATH) and os.path.exists(VECTORIZER_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                self.vectorizer = joblib.load(VECTORIZER_PATH)
                # classes_ is a numpy ndarray — never use `arr or []` (ambiguous truth value)
                _classes = getattr(self.model, "classes_", None)
                classes = list(_classes) if _classes is not None else []
                logger.info(
                    "Kategori modeli yüklendi (%s, classes=%s).",
                    type(self.model).__name__,
                    classes,
                )
            except Exception as e:
                logger.error(f"Model yükleme hatası: {e}")
                self.model = None
                self.vectorizer = None
        else:
            # Bu durum sessiz geçerse sistem "çalışıyor" görünüp ML doğruluğu tamamen
            # devre dışı kalıyor. Aranan yolu da yazıyoruz ki eksik olan görünür olsun.
            logger.info(
                "ML kategori modeli bulunamadı — kural tabanlı fallback kullanılacak. "
                "Aranan dizin: %s (category_model.joblib + vectorizer.joblib). "
                "Farklı bir konum için MODEL_DIR ortam değişkenini ayarlayın.",
                MODEL_DIR,
            )

    def reload_model(self) -> bool:
        """Force reload after retrain so holdout/eval sees fresh artifacts."""
        self.model = None
        self.vectorizer = None
        self.load_model()
        return self.model is not None and self.vectorizer is not None
    def clean_text(self, text: str) -> str:
        return normalize_turkish(text.translate(str.maketrans("", "", string.punctuation)))

    def _run_model(self, cleaned: str) -> Tuple[str, float]:
        vec = self.vectorizer.transform([cleaned])
        prediction = self.model.predict(vec)[0]
        try:
            probabilities = self.model.predict_proba(vec)[0]
            confidence = float(max(probabilities))
        except AttributeError:
            import numpy as np
            scores = self.model.decision_function(vec)[0]
            exp_scores = np.exp(scores - np.max(scores))
            confidence = float(exp_scores.max() / exp_scores.sum())
        # SGD may still emit legacy trainer labels — canonicalize to ALL_CATEGORIES
        return canonical_category(str(prediction)), round(confidence, 2)

    def _run_gemini(self, text: str, api_key: str) -> Tuple[str, float] | None:
        try:
            prompt = f"""
            Aşağıdaki otel yorumunu TEK bir departman kategorisine sınıflandır:
            {', '.join(ALL_CATEGORIES)}
            Yorum: "{text}"
            Sadece kategori adını yaz.
            """
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            import requests
            response = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if response.status_code == 200:
                raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                for category in ALL_CATEGORIES:
                    if category.lower() in raw.lower():
                        return category, 1.00
        except Exception as e:
            logger.warning(f"Gemini sınıflandırma hatası: {e}")
        return None

    def classify_category(
        self, text: str, api_key: str = None, use_gemini: bool = True
    ) -> Tuple[str, float, str, Optional[str], bool]:
        """
        Returns: category, confidence, method, secondary_category, is_mixed
        """
        cleaned = self.clean_text(text)
        rule_result: RuleClassificationResult = classify_by_rules(text)
        secondary = rule_result.secondary_category
        is_mixed = rule_result.is_mixed

        if rules_win_over_model(rule_result) or rule_result.confidence >= RULE_CONFIDENCE_WIN:
            self.last_method = "rules"
            cat = canonical_category(rule_result.category)
            sec = canonical_category(secondary) if secondary else secondary
            logger.info(
                f"Kategori [rules]: {cat} "
                f"(conf={rule_result.confidence}, mixed={is_mixed})"
            )
            return cat, rule_result.confidence, "rules", sec, is_mixed

        # Öncelik 2: SGD model — yüksek güven gerekli
        if self.model is not None and self.vectorizer is not None:
            try:
                model_cat, model_conf = self._run_model(cleaned)
                if model_conf >= MODEL_CONFIDENCE_MIN and not rules_win_over_model(rule_result):
                    self.last_method = "model"
                    logger.info(f"Kategori [model]: {model_cat} (conf={model_conf})")
                    return model_cat, model_conf, "model", (
                        canonical_category(secondary) if secondary else secondary
                    ), is_mixed
            except Exception as e:
                logger.error(f"Model tahmin hatası: {e}")

        # Öncelik 3: Gemini — yalnızca api_key ile
        if use_gemini:
            key = api_key or os.getenv("GEMINI_API_KEY")
            if key:
                gemini = self._run_gemini(text, key)
                if gemini:
                    self.last_method = "gemini"
                    cat, conf = gemini
                    cat = canonical_category(cat)
                    logger.info(f"Kategori [gemini]: {cat}")
                    return cat, conf, "gemini", (
                        canonical_category(secondary) if secondary else secondary
                    ), is_mixed

        # Öncelik 4: Kural fallback — güven skorunu asla 0.55 altına düşürme
        if rule_result.rule_score > 0 or len(cleaned.split()) >= 2:
            self.last_method = "fallback"
            conf = max(rule_result.confidence, CONFIDENCE_FALLBACK_MIN)
            cat = canonical_category(rule_result.category)
            logger.info(
                f"Kategori [fallback]: {cat} "
                f"(conf={conf}, score={rule_result.rule_score:.1f})"
            )
            return cat, conf, "fallback", (
                canonical_category(secondary) if secondary else secondary
            ), is_mixed

        self.last_method = "fallback"
        return CAT_OTHER, CONFIDENCE_FALLBACK_MIN, "fallback", None, False

    def retrain_model(self, corrected_data: List[Dict]) -> dict:
        try:
            if os.path.exists(CSV_PATH):
                df = pd.read_csv(CSV_PATH)
            else:
                df = pd.DataFrame(columns=["id", "comment", "category", "sentiment"])

            new_rows = []
            max_id = df["id"].max() if not df.empty else 0
            for i, item in enumerate(corrected_data):
                new_rows.append({
                    "id": max_id + i + 1,
                    "comment": item["comment"],
                    "category": item["category"],
                    "sentiment": item.get("sentiment", "NEGATIVE"),
                })
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
            df.to_csv(CSV_PATH, index=False)

            df["cleaned_comment"] = df["comment"].apply(self.clean_text)
            X, y = df["cleaned_comment"], df["category"]
            if len(y.unique()) < 2:
                return {"status": "error", "message": "En az 2 farklı kategori gerekli."}

            vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2))
            X_vec = vectorizer.fit_transform(X)
            model = MLPClassifier(
                hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                max_iter=300, random_state=42,
            )
            model.fit(X_vec, y)
            joblib.dump(model, MODEL_PATH)
            joblib.dump(vectorizer, VECTORIZER_PATH)
            self.model = model
            self.vectorizer = vectorizer
            return {"status": "success", "total_records": len(df), "message": "Model yeniden eğitildi."}
        except Exception as e:
            logger.error(f"Yeniden eğitim hatası: {e}")
            return {"status": "error", "message": str(e)}
