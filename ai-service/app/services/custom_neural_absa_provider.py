"""
Custom Neural ABSA Provider
Wraps the locally trained CustomHotelTransformer (.pt weights) for 100% private, zero-latency inference.
Designed for the Strategy Pattern without modifying rule-based engine.
"""
from __future__ import annotations

import os
import torch
from typing import Dict, Any, Tuple, Optional

from app.models.custom_hotel_transformer import (
    CustomHotelTransformer,
    CustomHotelTokenizer,
    ID2DEPT,
    ID2SENT,
    CANONICAL_DEPARTMENTS,
)


class CustomNeuralAbsaProvider:
    """Strategy Provider executing local custom Transformer inference."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        self.model_path = model_path or os.path.join(base_dir, "custom_hotel_transformer.pt")
        self.tokenizer_path = tokenizer_path or os.path.join(base_dir, "custom_hotel_tokenizer.json")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer: Optional[CustomHotelTokenizer] = None
        self.model: Optional[CustomHotelTransformer] = None
        self.is_ready = False

        self._load_artifacts()

    def _load_artifacts(self):
        if not os.path.exists(self.tokenizer_path) or not os.path.exists(self.model_path):
            print(f"[CustomNeuralAbsaProvider] Warning: Model/Tokenizer weights not found at {self.model_path}")
            return

        try:
            self.tokenizer = CustomHotelTokenizer.load(self.tokenizer_path)
            self.model = CustomHotelTransformer(
                vocab_size=len(self.tokenizer.vocab),
                d_model=128,
                nhead=4,
                num_layers=2,
                dim_feedforward=256,
                dropout=0.1,
            ).to(self.device)

            state_dict = torch.load(self.model_path, map_location=self.device, weights_only=True)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            self.is_ready = True
            print(f"[CustomNeuralAbsaProvider] Successfully loaded custom model on {self.device}")
        except Exception as e:
            print(f"[CustomNeuralAbsaProvider] Error loading custom model: {e}")
            self.is_ready = False

    def predict_clause(self, clause_text: str) -> Dict[str, Any]:
        """Perform neural inference on a single clause."""
        if not self.is_ready or not self.tokenizer or not self.model:
            return {"error": "Custom neural model not initialized", "department": "genel_diger", "sentiment": "Neutral"}

        input_ids = torch.tensor([self.tokenizer.encode(clause_text, max_length=64)], dtype=torch.long).to(self.device)

        with torch.no_grad():
            dept_logits, sent_logits = self.model(input_ids)
            
            dept_probs = torch.softmax(dept_logits, dim=1)[0]
            sent_probs = torch.softmax(sent_logits, dim=1)[0]

            top_dept_idx = int(dept_probs.argmax().item())
            top_sent_idx = int(sent_probs.argmax().item())

            dept_name = ID2DEPT.get(top_dept_idx, "genel_diger")
            sent_name = ID2SENT.get(top_sent_idx, "Neutral")

            dept_confidence = float(dept_probs[top_dept_idx].item())
            sent_confidence = float(sent_probs[top_sent_idx].item())

        return {
            "clause": clause_text,
            "department": dept_name,
            "department_confidence": dept_confidence,
            "sentiment": sent_name,
            "sentiment_confidence": sent_confidence,
            "provider": "CustomLocalNeuralTransformer",
        }
