"""
Deep Hotel LLM Service — Production Inference & Generative Reasoning Engine.
Integrates trained CustomDeepHotelLLM model with ABSA and Operational Analytics pipeline.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Any, Optional
import torch

from app.models.custom_deep_hotel_llm import CustomDeepHotelLLM, DeepCausalTokenizer


class DeepHotelLLMService:
    """
    Production-ready wrapper for the Custom Deep Hotel Causal LLM.
    Provides fast, GPU-accelerated generative explanations for hotel feedback.
    """

    _instance: Optional["DeepHotelLLMService"] = None

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        tokenizer_path = os.path.join(base_dir, "deep_causal_tokenizer.json")
        model_path = os.path.join(base_dir, "deep_hotel_llm.pt")

        self.tokenizer = DeepCausalTokenizer.load(tokenizer_path)
        
        # Instantiate matching 6-layer 384-dim Ultra High-Capacity Causal GPT LLM
        self.model = CustomDeepHotelLLM(
            vocab_size=len(self.tokenizer.vocab),
            d_model=384,
            nhead=12,
            num_layers=6,
            dim_feedforward=768,
            dropout=0.1,
        ).to(self.device)

        if os.path.exists(model_path):
            state_dict = torch.load(model_path, map_location=self.device, weights_only=True)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            self.is_ready = True
            print(f"[DeepHotelLLMService] Model successfully loaded on {self.device}")
        else:
            self.is_ready = False
            print(f"[DeepHotelLLMService] Warning: {model_path} not found. Operating in fallback mode.")

    @classmethod
    def get_instance(cls) -> "DeepHotelLLMService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def generate_explanation(
        self,
        prompt: str,
        max_new_tokens: int = 40,
        temperature: float = 0.65,
        top_k: int = 20,
    ) -> str:
        """Generates contextual operational reasoning for a given review prompt."""
        if not self.is_ready:
            return f"Operational analysis for: {prompt}"

        generated_text = self.model.generate(
            tokenizer=self.tokenizer,
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
        )
        return generated_text

    def enrich_absa_aspect(self, aspect_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches an ABSA aspect result with LLM-generated operational rationale.
        """
        clause = aspect_dict.get("clause", "")
        dept = aspect_dict.get("department", "Genel")
        sent = aspect_dict.get("sentiment", "Neutral")

        if not clause or not self.is_ready:
            return aspect_dict

        prompt = f"{clause}"
        explanation = self.generate_explanation(prompt, max_new_tokens=30, temperature=0.6)
        
        aspect_dict["llm_explanation"] = explanation
        aspect_dict["llm_status"] = "enriched"
        return aspect_dict
