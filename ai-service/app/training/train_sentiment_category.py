import os, sys, re, string, logging, warnings
warnings.filterwarnings("ignore")

# Ensure app package is importable
_script_dir = os.path.dirname(os.path.abspath(__file__))
_app_root = os.path.dirname(os.path.dirname(_script_dir))
if _app_root not in sys.path:
    sys.path.insert(0, _app_root)

import pandas as pd
import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

from app.services.turkish_nlp_utils import normalize_turkish, ALL_CATEGORIES

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("trainer")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(PROJECT_ROOT, "simulation")
CSV_PATH = os.path.join(DATA_DIR, "processed_reviews_25k.csv")
SYNTH_PATH = os.path.join(DATA_DIR, "synthetic_reviews.csv")

SENT_MODEL_PATH = os.path.join(DATA_DIR, "sentiment_model.joblib")
SENT_VEC_PATH = os.path.join(DATA_DIR, "sentiment_vectorizer.joblib")
CAT_MODEL_PATH = os.path.join(DATA_DIR, "category_model.joblib")
CAT_VEC_PATH = os.path.join(DATA_DIR, "vectorizer.joblib")


def clean_text(text: str) -> str:
    t = text.translate(str.maketrans("", "", string.punctuation))
    return normalize_turkish(t)


def rating_to_sentiment(r):
    if r <= 2:
        return "NEGATIVE"
    elif r >= 4:
        return "POSITIVE"
    return "NEUTRAL"


def main():
    log.info(f"Loading dataset from {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["translated_comment"]).copy()
    log.info(f"Loaded {len(df)} reviews")

    df["cleaned"] = df["translated_comment"].apply(clean_text)

    # ---- Sentiment ----
    # Strategy: train binary classifier (POSITIVE vs NEGATIVE) using only confident labels (rating 1-2, 4-5)
    # For NEUTRAL, we'll rely on the rule-based system (it's better at detecting mixed/neutral reviews)
    log.info("\n=== Sentiment Model Training (Binary: POSITIVE vs NEGATIVE) ===")

    df_bin = df[df["rating"].isin([1, 2, 4, 5])].copy()
    df_bin["sentiment_label"] = df_bin["rating"].apply(rating_to_sentiment)
    log.info(f"Binary label distribution: {df_bin['sentiment_label'].value_counts().to_dict()}")
    log.info(f"Training on {len(df_bin)} confident samples (ratings 1-2, 4-5)")

    X_s = df_bin["cleaned"]
    y_s = df_bin["sentiment_label"]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_s, y_s, test_size=0.2, random_state=42, stratify=y_s
    )

    sent_vec = TfidfVectorizer(
        max_features=15000, ngram_range=(1, 3), sublinear_tf=True,
        analyzer="char_wb", max_df=0.85, min_df=3,
    )
    sent_clf = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=1000,
        random_state=42,
    )

    log.info("Training binary sentiment model on %d samples...", len(X_tr))
    X_tr_vec = sent_vec.fit_transform(X_tr)
    sent_clf.fit(X_tr_vec, y_tr)

    X_te_vec = sent_vec.transform(X_te)
    y_pred = sent_clf.predict(X_te_vec)
    log.info(f"Binary accuracy: {accuracy_score(y_te, y_pred):.3f}")
    log.info(classification_report(y_te, y_pred, digits=3))

    joblib.dump(sent_vec, SENT_VEC_PATH)
    joblib.dump(sent_clf, SENT_MODEL_PATH)
    log.info(f"Sentiment model -> {SENT_MODEL_PATH}")

    # ---- Category ----
    log.info("\n=== Category Model Training ===")
    log.info(f"Category distribution:\n{df['category'].value_counts().to_string()}")

    df_cat = df[["cleaned", "category"]].copy()

    if os.path.exists(SYNTH_PATH):
        synth = pd.read_csv(SYNTH_PATH)
        if "text" in synth.columns and "category" in synth.columns:
            synth = synth.dropna(subset=["text", "category"]).copy()
            synth["cleaned"] = synth["text"].apply(clean_text)
            synth = synth[synth["category"].isin(ALL_CATEGORIES)]
            log.info(f"Adding {len(synth)} synthetic reviews")
            df_cat = pd.concat([df_cat, synth[["cleaned", "category"]]], ignore_index=True)

    log.info(f"Total category training samples: {len(df_cat)}")

    X_c = df_cat["cleaned"]
    y_c = df_cat["category"]

    X_tr_c, X_te_c, y_tr_c, y_te_c = train_test_split(
        X_c, y_c, test_size=0.2, random_state=42, stratify=y_c
    )

    cat_vec = TfidfVectorizer(
        max_features=20000, ngram_range=(1, 3), sublinear_tf=True,
        analyzer="char_wb", max_df=0.85, min_df=3,
    )
    cat_clf = MLPClassifier(
        hidden_layer_sizes=(256, 128, 64), activation="relu", solver="adam",
        alpha=0.01, max_iter=500, random_state=42,
        early_stopping=True, validation_fraction=0.1,
    )

    log.info("Training category model on %d samples...", len(X_tr_c))
    X_tr_c_vec = cat_vec.fit_transform(X_tr_c)
    cat_clf.fit(X_tr_c_vec, y_tr_c)

    X_te_c_vec = cat_vec.transform(X_te_c)
    y_pred_c = cat_clf.predict(X_te_c_vec)
    log.info(f"Category accuracy: {accuracy_score(y_te_c, y_pred_c):.3f}")
    log.info(classification_report(y_te_c, y_pred_c, digits=3))

    joblib.dump(cat_vec, CAT_VEC_PATH)
    joblib.dump(cat_clf, CAT_MODEL_PATH)
    log.info(f"Category model -> {CAT_MODEL_PATH}")

    log.info("\n=== Done ===")
    for p in [SENT_MODEL_PATH, SENT_VEC_PATH, CAT_MODEL_PATH, CAT_VEC_PATH]:
        sz = os.path.getsize(p) / 1024
        log.info(f"  {os.path.basename(p)}: {sz:.0f}KB")


if __name__ == "__main__":
    main()
