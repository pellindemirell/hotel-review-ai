"""
Custom Hotel Generative Causal Decoder Transformer LLM (Built From Scratch in PyTorch)
GPT / Gemini / LLaMA style Causal Decoder Architecture with Token Generation capability.

Features:
- Causal Masked Multi-Head Self-Attention
- Autoregressive Text Generation (generate() with Top-K / Temperature)
- 100% Local, Private, Zero External Dependencies
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Dict, List, Tuple, Any, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


class CustomCausalTokenizer:
    """Word & Subword Tokenizer for Generative Causal Text Generation."""

    PAD_TOKEN = "<pad>"
    UNK_TOKEN = "<unk>"
    BOS_TOKEN = "<bos>"
    EOS_TOKEN = "<eos>"

    def __init__(self, vocab: Optional[Dict[str, int]] = None):
        self.special_tokens = [self.PAD_TOKEN, self.UNK_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN]
        if vocab:
            self.vocab = vocab
        else:
            self.vocab = {tok: idx for idx, tok in enumerate(self.special_tokens)}
        self.inv_vocab = {idx: tok for tok, idx in self.vocab.items()}

    def build_vocab(self, texts: List[str], max_vocab_size: int = 8000, min_freq: int = 1):
        freqs: Dict[str, int] = {}
        for text in texts:
            tokens = self._tokenize_raw(text)
            for tok in tokens:
                freqs[tok] = freqs.get(tok, 0) + 1

        sorted_tokens = sorted(freqs.items(), key=lambda x: x[1], reverse=True)
        self.vocab = {tok: idx for idx, tok in enumerate(self.special_tokens)}
        for tok, count in sorted_tokens:
            if count < min_freq:
                continue
            if len(self.vocab) >= max_vocab_size:
                break
            if tok not in self.vocab:
                self.vocab[tok] = len(self.vocab)

        self.inv_vocab = {idx: tok for tok, idx in self.vocab.items()}

    def _tokenize_raw(self, text: str) -> List[str]:
        text = text.lower()
        return re.findall(r"[a-zçğıöşü0-9]+|[.,!?]", text)

    def encode(self, text: str, add_special: bool = True) -> List[int]:
        raw_tokens = self._tokenize_raw(text)
        tokens = ([self.BOS_TOKEN] if add_special else []) + raw_tokens + ([self.EOS_TOKEN] if add_special else [])
        return [self.vocab.get(tok, self.vocab[self.UNK_TOKEN]) for tok in tokens]

    def decode(self, ids: List[int]) -> str:
        tokens = []
        for i in ids:
            tok = self.inv_vocab.get(i, self.UNK_TOKEN)
            if tok in (self.PAD_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN):
                continue
            tokens.append(tok)
        
        # Clean up punctuation formatting
        text = " ".join(tokens)
        text = re.sub(r"\s+([.,!?])", r"\1", text)
        return text

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "CustomCausalTokenizer":
        with open(filepath, "r", encoding="utf-8") as f:
            vocab = json.load(f)
        return cls(vocab)


class CausalPositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


class CustomHotelCausalLLM(nn.Module):
    """
    Generative Causal LLM (ChatGPT / Gemini Style) built from scratch.
    Architecture:
      - Token Embedding + Positional Encoding
      - Causal Decoder Transformer Layers with Masked Attention
      - Token Predictor Head (LM Head)
      - Autoregressive Generation Engine
    """

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 256,
        nhead: int = 8,
        num_layers: int = 4,
        dim_feedforward: int = 512,
        dropout: float = 0.1,
        pad_idx: int = 0,
    ):
        super().__init__()
        self.d_model = d_model
        self.vocab_size = vocab_size
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=pad_idx)
        self.pos_encoder = CausalPositionalEncoding(d_model)

        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.lm_head = nn.Linear(d_model, vocab_size)

        self._init_weights()

    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def _generate_causal_mask(self, seq_len: int, device: torch.device) -> torch.Tensor:
        mask = torch.triu(torch.ones(seq_len, seq_len, device=device), diagonal=1).bool()
        return mask

    def forward(self, input_ids: torch.Tensor, memory: Optional[torch.Tensor] = None) -> torch.Tensor:
        seq_len = input_ids.size(1)
        device = input_ids.device
        causal_mask = self._generate_causal_mask(seq_len, device)

        x = self.embedding(input_ids) * math.sqrt(self.d_model)
        x = self.pos_encoder(x)

        # Memory dummy tensor if None (Decoder-only mode)
        if memory is None:
            memory = torch.zeros(input_ids.size(0), 1, self.d_model, device=device)

        out = self.transformer_decoder(
            tgt=x,
            memory=memory,
            tgt_mask=causal_mask,
        )

        logits = self.lm_head(out)
        return logits

    @torch.no_grad()
    def generate(
        self,
        tokenizer: CustomCausalTokenizer,
        prompt: str,
        max_new_tokens: int = 50,
        temperature: float = 0.7,
        top_k: int = 10,
    ) -> str:
        """Autoregressive text generation like ChatGPT / Gemini."""
        self.eval()
        device = next(self.parameters()).device

        prompt_ids = tokenizer.encode(prompt, add_special=False)
        input_ids = torch.tensor([[tokenizer.vocab[tokenizer.BOS_TOKEN]] + prompt_ids], dtype=torch.long, device=device)

        for _ in range(max_new_tokens):
            logits = self(input_ids)
            next_token_logits = logits[0, -1, :] / max(temperature, 1e-5)

            # Top-K sampling
            if top_k > 0:
                indices_to_remove = next_token_logits < torch.topk(next_token_logits, top_k)[0][..., -1, None]
                next_token_logits[indices_to_remove] = -float("Inf")

            probs = torch.softmax(next_token_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1).unsqueeze(0)

            if next_token.item() == tokenizer.vocab[tokenizer.EOS_TOKEN]:
                break

            input_ids = torch.cat([input_ids, next_token], dim=1)

        generated_ids = input_ids[0].tolist()
        return tokenizer.decode(generated_ids)
