"""
Custom Hotel Transformer Architecture (Built From Scratch in PyTorch)
Designed specifically for Hotel & Restaurant ABSA (8 Departments + Sentiment).

No third-party pre-trained LLM weights used. Fully local, private, and lightweight.
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

# 8 Canonical Departments in exact project order
CANONICAL_DEPARTMENTS = [
    "yiyecek_icecek",
    "oda_temizlik",
    "on_buro",
    "personel",
    "teknik_servis",
    "spa_rekreasyon",
    "fiyat_fatura",
    "genel_diger",
]

DEPT2ID = {dept: idx for idx, dept in enumerate(CANONICAL_DEPARTMENTS)}
ID2DEPT = {idx: dept for idx, dept in enumerate(CANONICAL_DEPARTMENTS)}

SENTIMENT_LABELS = ["Positive", "Negative", "Neutral"]
SENT2ID = {label: idx for idx, label in enumerate(SENTIMENT_LABELS)}
ID2SENT = {idx: label for idx, label in enumerate(SENTIMENT_LABELS)}


class CustomHotelTokenizer:
    """Fast, domain-specific word & subword tokenizer built from scratch."""

    PAD_TOKEN = "[PAD]"
    UNK_TOKEN = "[UNK]"
    CLS_TOKEN = "[CLS]"
    SEP_TOKEN = "[SEP]"

    def __init__(self, vocab: Optional[Dict[str, int]] = None):
        self.special_tokens = [self.PAD_TOKEN, self.UNK_TOKEN, self.CLS_TOKEN, self.SEP_TOKEN]
        if vocab:
            self.vocab = vocab
        else:
            self.vocab = {tok: idx for idx, tok in enumerate(self.special_tokens)}
        self.inv_vocab = {idx: tok for tok, idx in self.vocab.items()}

    def build_vocab(self, texts: List[str], max_vocab_size: int = 10000, min_freq: int = 1):
        """Build vocabulary from domain corpus."""
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
        # Keep Turkish characters & words
        tokens = re.findall(r"[a-zçğıöşü0-9]+", text)
        return tokens

    def encode(self, text: str, max_length: int = 64) -> List[int]:
        tokens = [self.CLS_TOKEN] + self._tokenize_raw(text)[: max_length - 2] + [self.SEP_TOKEN]
        ids = [self.vocab.get(tok, self.vocab[self.UNK_TOKEN]) for tok in tokens]
        
        # Pad sequence
        if len(ids) < max_length:
            ids += [self.vocab[self.PAD_TOKEN]] * (max_length - len(ids))
        else:
            ids = ids[:max_length]
        return ids

    def decode(self, ids: List[int]) -> str:
        tokens = [self.inv_vocab.get(i, self.UNK_TOKEN) for i in ids if i not in (
            self.vocab[self.PAD_TOKEN], self.vocab[self.CLS_TOKEN], self.vocab[self.SEP_TOKEN]
        )]
        return " ".join(tokens)

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "CustomHotelTokenizer":
        with open(filepath, "r", encoding="utf-8") as f:
            vocab = json.load(f)
        return cls(vocab)


class PositionalEncoding(nn.Module):
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


class CustomHotelTransformer(nn.Module):
    """
    Custom Deep Learning Model (PyTorch) built from scratch.
    Architecture:
      - Token Embedding + Positional Encoding
      - Multi-Head Self-Attention Transformer Encoder (2 Layers)
      - Dual Task Classifier Heads:
          1) 8-Department Logits Classifier Head
          2) Sentiment Logits Classifier Head
    """

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        pad_idx: int = 0,
    ):
        super().__init__()
        self.d_model = d_model
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=pad_idx)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        self.dropout = nn.Dropout(dropout)
        
        # Dual heads for 8-Department classification & Sentiment classification
        self.dept_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, len(CANONICAL_DEPARTMENTS)),
        )
        
        self.sentiment_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, len(SENTIMENT_LABELS)),
        )

        self._init_weights()

    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, input_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        # Embeddings & Positional Encodings
        x = self.embedding(input_ids) * math.sqrt(self.d_model)
        x = self.pos_encoder(x)
        
        # Padding mask for transformer
        src_key_padding_mask = (input_ids == 0) if attention_mask is None else (attention_mask == 0)
        
        # Transformer Self-Attention Pass
        encoded = self.transformer_encoder(x, src_key_padding_mask=src_key_padding_mask)
        
        # Global Average Pooling over non-padded tokens
        if src_key_padding_mask is not None:
            mask = (~src_key_padding_mask).unsqueeze(-1).float()
            pooled = (encoded * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        else:
            pooled = encoded.mean(dim=1)

        pooled = self.dropout(pooled)

        dept_logits = self.dept_head(pooled)
        sent_logits = self.sentiment_head(pooled)

        return dept_logits, sent_logits
