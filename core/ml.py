from __future__ import annotations
import json, os
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel, logging as hf_logging
from django.conf import settings

hf_logging.set_verbosity_error()

NUM_TYPES = 20
INCLUDE_BIN_HEAD = True

class MultiHeadClassifier(nn.Module):
    def __init__(self, base_model_name: str = "roberta-large", dropout: float = 0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(base_model_name, add_pooling_layer=False)
        hidden = self.backbone.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.sev_head = nn.Sequential(nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(0.1), nn.Linear(hidden, 4))
        self.types_head = nn.Linear(hidden, NUM_TYPES)
        if INCLUDE_BIN_HEAD:
            self.bin_head = nn.Linear(hidden, 1)

    def forward(self, input_ids=None, attention_mask=None, token_type_ids=None, **kwargs):
        out = self.backbone(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=None, **kwargs)
        last = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        h = (last * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
        h = self.dropout(h)
        logits = {"logits_sev": self.sev_head(h), "logits_types": self.types_head(h)}
        if INCLUDE_BIN_HEAD:
            logits["logits_bin"] = self.bin_head(h).squeeze(-1)
        return logits

def _strip_module_prefix(state_dict: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    out: Dict[str, torch.Tensor] = {}
    for k, v in state_dict.items():
        out[k[len("module."):] if k.startswith("module.") else k] = v
    return out

def load_multitask_from_dir(run_dir: str | Path, base_backbone: str = "roberta-large", map_location="cpu") -> MultiHeadClassifier:
    run_dir = Path(run_dir)
    model = MultiHeadClassifier(base_model_name=base_backbone)
    model.to(map_location)

    st_path = run_dir / "model.safetensors"
    if st_path.exists():
        from safetensors.torch import load_file
        state = load_file(st_path.as_posix(), device="cpu")
        state = _strip_module_prefix(state)
        model.load_state_dict(state, strict=False)
        return model

    bin_path = run_dir / "pytorch_model.bin"
    if bin_path.exists():
        state = torch.load(bin_path.as_posix(), map_location="cpu")
        state = _strip_module_prefix(state)
        model.load_state_dict(state, strict=False)
        return model

    return model  # sin pesos: sirve para pruebas

def _resolve_device(req: Optional[str]) -> str:
    req = (req or os.getenv("DEVICE") or "cpu").lower()
    if req in ("auto", "none", ""):
        if torch.cuda.is_available(): return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available(): return "mps"
        return "cpu"
    return req if req in ("cpu", "cuda", "mps") else "cpu"

class VulnClassifier:
    _instance: "VulnClassifier | None" = None

    def __init__(self, run_dir: str | Path, device: str = "cpu", max_length: int = 512):
        self.run_dir_path = Path(run_dir)
        self.run_dir = str(self.run_dir_path)
        self.model_name = getattr(settings, "MODEL_NAME", "roberta-large")
        self.device = torch.device(_resolve_device(device))
        self.max_length = max_length

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.run_dir_path.as_posix(), use_fast=True)
        except Exception:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token or self.tokenizer.cls_token

        self.model = load_multitask_from_dir(self.run_dir_path, base_backbone=self.model_name, map_location="cpu").to(self.device).eval()

        self.bin_threshold = 0.5
        tpath = self.run_dir_path / "binary_threshold.txt"
        if tpath.exists():
            try: self.bin_threshold = float(tpath.read_text().strip())
            except Exception: pass
        override = getattr(settings, "BIN_THRESHOLD", None)
        if override is not None:
            try: self.bin_threshold = float(override)
            except Exception: pass
        mpath = self.run_dir_path / "metrics.json"
        if mpath.exists():
            try:
                meta = json.loads(mpath.read_text())
                if "binary_threshold" in meta:
                    self.bin_threshold = float(meta["binary_threshold"])
            except Exception: pass

        thr_path = self.run_dir_path / "types_thresholds.npy"
        self.type_thresholds = np.load(thr_path) if thr_path.exists() else np.full((NUM_TYPES,), 0.5, dtype=np.float32)

        labels_path = self.run_dir_path / "type_labels.json"
        if labels_path.exists():
            try: self.type_labels: List[str] = json.loads(labels_path.read_text())
            except Exception: self.type_labels = [f"type_{i}" for i in range(len(self.type_thresholds))]
        else:
            self.type_labels = [f"type_{i}" for i in range(len(self.type_thresholds))]

    @classmethod
    def instance(cls) -> "VulnClassifier":
        if cls._instance is None:
            run_dir = getattr(settings, "RUN_DIR", "./models/current")
            device = getattr(settings, "DEVICE", "cpu")
            cls._instance = VulnClassifier(run_dir, device=device)
        return cls._instance

    def _encode(self, text: str) -> Dict[str, torch.Tensor]:
        enc = self.tokenizer(text, padding=False, truncation=True, max_length=self.max_length, return_tensors="pt")
        return {k: v.to(self.device) for k, v in enc.items()}

    @torch.inference_mode()
    def predict(self, text: str) -> Dict[str, Any]:
        enc = self._encode(text)
        out = self.model(**enc)

        logits_bin = out.get("logits_bin")
        bin_score = None
        bin_is_vuln = None
        if logits_bin is not None:
            bin_score = torch.sigmoid(logits_bin).item()
            bin_is_vuln = bool(bin_score >= self.bin_threshold)

        types_pred: List[str] = []
        types_probs: Dict[str, float] | None = None
        severity_pred: int | None = None
        severity_probs: List[float] | None = None

        if (bin_is_vuln is None) or bin_is_vuln:
            logits_types = out["logits_types"]
            logits_sev = out["logits_sev"]
            t_probs = torch.sigmoid(logits_types).squeeze(0).cpu().numpy()
            s_probs = F.softmax(logits_sev, dim=-1).squeeze(0).cpu().numpy()
            thr = self.type_thresholds if len(self.type_thresholds) == len(t_probs) else np.full_like(t_probs, 0.5)
            mask = t_probs >= thr
            types_pred = [self.type_labels[i] for i, m in enumerate(mask) if m]
            if (bin_is_vuln is not None) and (not bin_is_vuln):
                types_pred = []
                t_probs = np.zeros_like(t_probs)
            types_probs = {self.type_labels[i]: float(t_probs[i]) for i in range(len(self.type_labels))}
            severity_pred = int(np.argmax(s_probs))
            severity_probs = [float(x) for x in s_probs.tolist()]

        return {
            "bin_is_vuln": bin_is_vuln,
            "bin_score": float(bin_score) if bin_score is not None else None,
            "types_pred": types_pred,
            "types_probs": types_probs,
            "severity_pred": severity_pred,
            "severity_probs": severity_probs,
        }

def get_classifier() -> VulnClassifier:
    return VulnClassifier.instance()
