"""
Deep Hotel Generative Causal Transformer LLM (Built From Scratch in PyTorch)
Ultra-Fast Pure Causal Self-Attention Transformer Architecture.
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


class DeepCausalTokenizer:
    """Subword & Word Tokenizer built for 20,000+ sentence corpus."""

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

    def build_vocab(self, texts: List[str], max_vocab_size: int = 10000, min_freq: int = 2):
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
        text = " ".join(tokens)
        text = re.sub(r"\s+([.,!?])", r"\1", text)
        return text

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "DeepCausalTokenizer":
        with open(filepath, "r", encoding="utf-8") as f:
            vocab = json.load(f)
        return cls(vocab)


class CausalBlock(nn.Module):
    def __init__(self, d_model: int, nhead: int, dim_feedforward: int, dropout: float = 0.1):
        super().__init__()
        self.attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        self.ln1 = nn.LayerNorm(d_model)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )
        self.ln2 = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, attn_mask: torch.Tensor) -> torch.Tensor:
        # Multi-Head Causal Self-Attention
        norm_x = self.ln1(x)
        attn_out, _ = self.attn(norm_x, norm_x, norm_x, attn_mask=attn_mask)
        x = x + attn_out
        # Feed-Forward MLP
        x = x + self.mlp(self.ln2(x))
        return x


class CustomDeepHotelLLM(nn.Module):
    """
    High-Capacity Causal Decoder Transformer (GPT-2 / LLaMA Architecture from Scratch).
    """

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 384,
        nhead: int = 12,
        num_layers: int = 6,
        dim_feedforward: int = 1024,
        dropout: float = 0.1,
        pad_idx: int = 0,
    ):
        super().__init__()
        self.d_model = d_model
        self.vocab_size = vocab_size
        self.tok_emb = nn.Embedding(vocab_size, d_model, padding_idx=pad_idx)
        self.pos_emb = nn.Embedding(512, d_model)

        self.blocks = nn.ModuleList([
            CausalBlock(d_model, nhead, dim_feedforward, dropout) for _ in range(num_layers)
        ])
        self.ln_f = nn.LayerNorm(d_model)
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)

        # Tie weights
        self.lm_head.weight = self.tok_emb.weight

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        b, t = input_ids.size()
        device = input_ids.device

        pos = torch.arange(0, t, dtype=torch.long, device=device).unsqueeze(0)
        x = self.tok_emb(input_ids) + self.pos_emb(pos)

        causal_mask = torch.triu(torch.ones(t, t, device=device), diagonal=1).bool()

        for block in self.blocks:
            x = block(x, causal_mask)

        x = self.ln_f(x)
        logits = self.lm_head(x)
        return logits

    @torch.no_grad()
    def generate(
        self,
        tokenizer: DeepCausalTokenizer,
        prompt: str,
        max_new_tokens: int = 60,
        temperature: float = 0.7,
        top_k: int = 15,
    ) -> str:
        self.eval()
        device = next(self.parameters()).device

        prompt_ids = tokenizer.encode(prompt, add_special=False)
        input_ids = torch.tensor([[tokenizer.vocab[tokenizer.BOS_TOKEN]] + prompt_ids], dtype=torch.long, device=device)

        for _ in range(max_new_tokens):
            if input_ids.size(1) >= 512:
                break
            logits = self(input_ids)
            next_token_logits = logits[0, -1, :] / max(temperature, 1e-5)

            if top_k > 0:
                indices_to_remove = next_token_logits < torch.topk(next_token_logits, top_k)[0][..., -1, None]
                next_token_logits[indices_to_remove] = -float("Inf")

            probs = torch.softmax(next_token_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1).unsqueeze(0)

            if next_token.item() == tokenizer.vocab[tokenizer.EOS_TOKEN]:
                break

            input_ids = torch.cat([input_ids, next_token], dim=1)

        return tokenizer.decode(input_ids[0].tolist())
