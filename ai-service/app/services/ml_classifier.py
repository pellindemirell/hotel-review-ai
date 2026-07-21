"""
BERTurk clause classifier — loads trained model from simulation/berturk_clause_model
and returns department predictions with confidence scores.
"""
from __future__ import annotations

import json
import os
import logging
from functools import lru_cache
from typing import Optional

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)

_CANDIDATE_DIRS = [
    os.environ.get("BERTURK_MODEL_DIR"),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "simulation", "berturk_clause_model")),
    r"D:\KodYazılımStaj1\simulation\berturk_clause_model",
]
_MODEL_DIR = None
for _d in _CANDIDATE_DIRS:
    if _d and os.path.isdir(_d) and os.path.isfile(os.path.join(_d, "model.safetensors")):
        _MODEL_DIR = _d
        break
if _MODEL_DIR is None:
    _MODEL_DIR = _CANDIDATE_DIRS[1] or _CANDIDATE_DIRS[2]
    logger.warning("BERTurk model not found at any candidate path, will use: %s", _MODEL_DIR)

CANONICAL = [
    "Kat Hizmetleri & Temizlik", "Yiyecek & İçecek",
    "Ön Büro & Misafir İlişkileri", "Teknik Servis & IT",
    "Rekreasyon & Eğlence", "Çevre, Güvenlik & Ulaşım",
    "Otel Atmosferi & Misafir Profili", "Personel Davranışı",
]
LABEL2ID = {d: i for i, d in enumerate(CANONICAL)}
ID2LABEL = {i: d for d, i in LABEL2ID.items()}


@lru_cache(maxsize=1)
def _load_model():
    if not os.path.isdir(_MODEL_DIR):
        logger.warning("BERTurk model directory not found: %s", _MODEL_DIR)
        return None, None
    try:
        tok = AutoTokenizer.from_pretrained(_MODEL_DIR)
        model = AutoModelForSequenceClassification.from_pretrained(_MODEL_DIR)
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        logger.info("BERTurk model loaded from %s (device=%s)", _MODEL_DIR, device)
        return tok, model
    except Exception as e:
        logger.warning("Failed to load BERTurk model: %s", e)
        return None, None


def classify_berturk(text: str) -> Optional[dict]:
    tok, model = _load_model()
    if tok is None or model is None:
        return None
    try:
        inputs = tok(text, truncation=True, padding=True, max_length=128, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = F.softmax(logits, dim=1)
        top_prob, top_idx = probs.max(dim=1)
        pred_idx = top_idx.item()
        confidence = top_prob.item()
        return {
            "department": ID2LABEL[pred_idx],
            "confidence": confidence,
            "all_probs": {ID2LABEL[i]: float(probs[0][i]) for i in range(len(CANONICAL))},
        }
    except Exception as e:
        logger.warning("BERTurk inference error: %s", e)
        return None


def predict_department(text: str, fallback: Optional[str] = None) -> tuple[str, float]:
    result = classify_berturk(text)
    if result and result["confidence"] >= 0.7:
        return result["department"], result["confidence"]
    return fallback or "Otel Atmosferi & Misafir Profili", 0.0
