"""
Operational Embedding Pipeline — semantic understanding layer for HODIP.

Replaces regex-based pattern matching with learned embeddings.
Every clause is mapped to a 384-dim operational vector where similar
operational problems are close together.

"havlu gelmedi" ≈ "diş fırçası gelmedi" ≈ "terlik bırakılmamış"
    → all near "Amenity Delivery Failure" vector

Architecture:
    - Phase 1 (cold start): rule fallback + static embeddings from known patterns
    - Phase 2 (warm): sentence-transformers with contrastive learning
    - Phase 3 (mature): fine-tuned Turkish-BERT operational embedder
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

import numpy as np

from ..knowledge_graph import _OBSERVATION_PATTERNS, _normalize

# ---------------------------------------------------------------------------
# Cold-start: static embeddings generated from known pattern clauses
# ---------------------------------------------------------------------------

# Representative clause per failure type for cold-start embedding
_PROTOTYPE_CLAUSES: dict[str, list[str]] = {
    "kus_yuvasi": ["odaya kuş yuvası vardı", "balkonda kuş yuvası", "pencere kenarı kuş pisliği", "kuşlar yuva yapmış"],
    "dis_fircasi": ["diş fırçası gelmedi", "diş fırçası yoktu", "fırça getirmediler"],
    "havlu_alinmis": ["havluları aldılar yenisi yok", "temiz havlu bırakmamışlar", "havlu değişmemiş"],
    "takip_eksik": ["sürekli hatırlatmak gerekiyor", "kaç kez söyledik", "takip eden yok"],
    "yemek_kalite": ["yemekler kötüydü", "lezzet yok", "çeşit çok az"],
    "icecek_yetersiz": ["içecek az", "içecek çeşidi yok", "susuz kaldık"],
    "kokteyl_bilmiyor": ["kokteyl nedir bilmiyorlar", "kokteyl yapamıyorlar", "bar bilmiyor"],
    "personel_egitimsiz": ["personel eğitimsiz", "garson bilmiyor", "hizmet anlayışı yok"],
    "denetim_yok": ["denetim yok", "hiç kontrol eden yok", "ilgilenen yok"],
    "oda_temizlenmemis": ["oda temizlenmemiş", "temizlik yapılmamış", "kirli bırakılmış"],
    "hijyen_eksik": ["hijyen yok", "temiz değil", "pis"],
    "tavsiye_etmiyor": ["tavsiye etmiyorum", "önermiyorum", "gelmem"],
    "havlu_sorunu": ["havlu getirmediler", "havlu istedim gelmedi", "temiz havlu yok", "havlu vermediler"],
}

_FAILURE_LABELS: list[str] = list(_PROTOTYPE_CLAUSES.keys())

# Simple character-level features for cold-start similarity
def _char_ngram_features(text: str, n: int = 3) -> set[str]:
    norm = _normalize(text)
    return {norm[i:i + n] for i in range(len(norm) - n + 1)}


def _jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class EmbeddingResult:
    failure_key: str
    label: str
    similarity: float
    method: str  # "exact_match" | "jaccard" | "embedding"
    confidence: float
    evidence: list[str] = field(default_factory=list)


class OperationalEmbedder:
    """
    Converts a clause into an operational vector and finds the closest failure type.

    Cold-start: Jaccard similarity on char n-grams + rule fallback
    Mature: Sentence-BERT embedding + FAISS index
    """

    def __init__(self) -> None:
        self._prototype_cache: dict[str, list[set[str]]] = {}
        self._cold_start = True
        self._sentence_model = None
        self._faiss_index = None
        self._build_prototype_cache()

    def _build_prototype_cache(self) -> None:
        for key, clauses in _PROTOTYPE_CLAUSES.items():
            self._prototype_cache[key] = [_char_ngram_features(c) for c in clauses]

    def embed(self, text: str) -> np.ndarray:
        """Return operational embedding (384-dim placeholder for cold start)."""
        if self._cold_start:
            return self._cold_embed(text)
        return self._model_embed(text)

    def _cold_embed(self, text: str) -> np.ndarray:
        """Char n-gram frequency vector as poor man's embedding (384 dim)."""
        features = _char_ngram_features(text)
        vec = np.zeros(384, dtype=np.float32)
        for i, ch in enumerate(_normalize(text)[:384]):
            vec[i % 384] += ord(ch) / 255.0
        return vec / (np.linalg.norm(vec) + 1e-8)

    def _model_embed(self, text: str) -> np.ndarray:
        try:
            if self._sentence_model is None:
                from sentence_transformers import SentenceTransformer
                self._sentence_model = SentenceTransformer(
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
            return self._sentence_model.encode([text], normalize_embeddings=True)[0]
        except Exception:
            logger.warning("Sentence transformer encode failed, using cold embed", exc_info=True)
            return self._cold_embed(text)

    def find_nearest_failure(
        self, clause: str, threshold: float = 0.15
    ) -> Optional[EmbeddingResult]:
        """Find closest failure type for a clause."""
        norm = _normalize(clause)

        # 1. Rule fallback — exact pattern match (always used)
        for key, info in _OBSERVATION_PATTERNS.items():
            pat = info["pattern"]
            if pat.search(norm) or pat.search(clause.lower()):
                return EmbeddingResult(
                    failure_key=key,
                    label=info["label"],
                    similarity=1.0,
                    method="exact_match",
                    confidence=0.95,
                    evidence=[clause],
                )

        # 2. Jaccard similarity (cold-start learned)
        query_features = _char_ngram_features(clause)
        best_sim = 0.0
        best_key = ""
        for key, prototypes in self._prototype_cache.items():
            for proto in prototypes:
                sim = _jaccard_similarity(query_features, proto)
                if sim > best_sim:
                    best_sim = sim
                    best_key = key

        if best_sim >= threshold and best_key:
            info = _OBSERVATION_PATTERNS.get(best_key, {})
            return EmbeddingResult(
                failure_key=best_key,
                label=info.get("label", best_key),
                similarity=best_sim,
                method="jaccard",
                confidence=min(0.7, best_sim * 0.9),
                evidence=[clause],
            )

        # 3. Model embedding (if available)
        if not self._cold_start:
            vec = self._model_embed(clause)
            if self._faiss_index is not None:
                distances, indices = self._faiss_index.search(vec.reshape(1, -1), 1)
                if distances[0][0] >= threshold:
                    idx = indices[0][0]
                    key = _FAILURE_LABELS[idx]
                    info = _OBSERVATION_PATTERNS.get(key, {})
                    return EmbeddingResult(
                        failure_key=key,
                        label=info.get("label", key),
                        similarity=float(distances[0][0]),
                        method="embedding",
                        confidence=float(distances[0][0]),
                        evidence=[clause],
                    )

        return None

    def train(self, labeled_clauses: list[tuple[str, str]]) -> None:
        """
        Train the embedder from labeled data.

        Args:
            labeled_clauses: list of (clause_text, failure_key)
        """
        if len(labeled_clauses) < 50:
            return

        try:
            texts = [c for c, _ in labeled_clauses]
            labels = [l for _, l in labeled_clauses]

            vecs = self._model_embed_batch(texts)

            import faiss

            dim = vecs.shape[1]
            index = faiss.IndexFlatIP(dim)
            index.add(vecs)

            self._faiss_index = index
            self._cold_start = False

            # Update prototype cache with learned representations
            for text, label in labeled_clauses:
                if label not in self._prototype_cache:
                    self._prototype_cache[label] = []
                ngram = _char_ngram_features(text)
                if ngram not in self._prototype_cache[label]:
                    self._prototype_cache[label].append(ngram)

        except ImportError:
            pass  # Keep cold start

    def _model_embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        if self._sentence_model is None:
            self._model_embed("")  # Lazy init
        if self._sentence_model is not None:
            return self._sentence_model.encode(texts, normalize_embeddings=True)
        return np.array([self._cold_embed(t) for t in texts])
