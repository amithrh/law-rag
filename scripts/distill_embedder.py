#!/usr/bin/env python3
"""Stage 4 — distill bge-m3 (1024-d teacher) → MiniLM-L12 (384-d student).

Approach (Phase A = KD-only):
  1. Load 100K teacher embeddings produced by extract_teacher_embeddings.py
     (already L2-normalised by bge-m3 inference path)
  2. Fit PCA(384) on the 100K teacher vectors → projection matrix W (1024×384)
  3. Per example, target = teacher @ W, then L2-renormalised → 384-d unit vector
  4. Train student (paraphrase-multilingual-MiniLM-L12-v2, native 384-d)
     to minimise MSE(student.encode(text), target)
  5. Save student + W matrix. At inference student.encode(text) is used directly;
     W is kept only for re-projecting the held-out teacher embeddings in eval.

Phase B (KD + InfoNCE + QAT, enabled with --phase b):
  Continue from Phase A checkpoint. Loss = 1.0×MSE + 0.3×InfoNCE_in_batch
  + 0.2×QAT(3-bit fake-quant on student output before MSE).

Gates:
  Phase A: held-out 5K mean cosine to teacher-projection ≥ 0.85
  Phase B: 500-query SSE eval pass-rate within −3pp of bge-m3 baseline

Wall (M4 Max MPS):
  Phase A:  ~12h  (100K × 1 epoch, batch 64)
  Phase B:  ~15h  (same data × 1 epoch, batch 32 + extras)

Usage:
  PYTHONPATH=. .venv/bin/python scripts/distill_embedder.py --phase a
  PYTHONPATH=. .venv/bin/python scripts/distill_embedder.py --phase b \
      --resume models/student_minilm_phaseA
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.decomposition import PCA
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).parent.parent
TRAINING_DIR = ROOT / "data/training"
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True, parents=True)

STUDENT_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_LEN = 256
EVAL_HOLDOUT = 5_000
SEED = 42

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("distill")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


class TeacherTargetDataset(Dataset):
    """Holds (text, target_384d) pairs.

    targets are pre-computed (PCA-projected teacher embeddings, L2-normalised).
    """

    def __init__(self, texts: list[str], targets: np.ndarray):
        assert len(texts) == targets.shape[0], "len mismatch"
        self.texts = texts
        self.targets = torch.from_numpy(targets).float()

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int):
        return self.texts[idx], self.targets[idx]


def collate(tokenizer):
    def _fn(batch):
        texts, targets = zip(*batch)
        enc = tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=MAX_LEN,
            return_tensors="pt",
        )
        return enc, torch.stack(targets)
    return _fn


# ---------------------------------------------------------------------------
# Student wrapper — mean-pool then L2-normalise. 384-d native output.
# ---------------------------------------------------------------------------


class StudentEncoder(torch.nn.Module):
    def __init__(self, model_name: str = STUDENT_NAME):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)

    def forward(self, input_ids, attention_mask):
        out = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        # mean-pool on token embeddings using attention mask
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (out.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return F.normalize(pooled, p=2, dim=1)


# ---------------------------------------------------------------------------
# QAT — symmetric per-channel 3-bit fake-quant on the 384-d output
# ---------------------------------------------------------------------------


def fake_quant_3bit(x: torch.Tensor) -> torch.Tensor:
    """Per-row symmetric quantize to 3 bits then de-quantize (straight-through)."""
    # Levels: {-3,-2,-1,0,1,2,3} (7 levels = 3-bit signed without -4)
    abs_max = x.abs().amax(dim=1, keepdim=True).clamp(min=1e-6)
    scale = abs_max / 3.0
    q = torch.clamp(torch.round(x / scale), -3, 3)
    dq = q * scale
    # straight-through: pass gradient unchanged
    return x + (dq - x).detach()


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------


def fit_pca_projection(teacher: np.ndarray, k: int = 384) -> np.ndarray:
    log.info("fitting PCA(%d) on teacher shape=%s ...", k, teacher.shape)
    p = PCA(n_components=k, svd_solver="randomized", random_state=SEED)
    p.fit(teacher)
    var = p.explained_variance_ratio_.sum()
    log.info("PCA done — top-%d explains %.3f of variance", k, var)
    return p.components_.T.astype(np.float32)  # (1024, 384)


def l2_normalise(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-9)
    return (x / n).astype(np.float32)


def run(args: argparse.Namespace) -> None:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    log.info("device=%s phase=%s", device, args.phase)

    # ---- Load extracted teacher data ----
    teacher_npy = TRAINING_DIR / "teacher_emb_100k.npy"
    teacher_jsonl = TRAINING_DIR / "teacher_emb_100k.jsonl"
    if not teacher_npy.exists():
        raise SystemExit(f"missing {teacher_npy} — run extract_teacher_embeddings.py first")
    teacher = np.load(teacher_npy)
    teacher = l2_normalise(teacher)
    texts: list[str] = []
    with teacher_jsonl.open() as f:
        for line in f:
            texts.append(json.loads(line)["text"])
    assert len(texts) == teacher.shape[0], "text/emb mismatch"
    log.info("loaded teacher: %d examples, dim=%d", *teacher.shape)

    # ---- Train/eval split (last EVAL_HOLDOUT) ----
    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(texts))
    train_idx, eval_idx = idx[:-EVAL_HOLDOUT], idx[-EVAL_HOLDOUT:]
    log.info("train=%d eval=%d", len(train_idx), len(eval_idx))

    # ---- PCA fit on train only (no leakage) ----
    W = fit_pca_projection(teacher[train_idx])  # (1024, 384)
    np.save(MODELS_DIR / "pca_W_1024_384.npy", W)
    targets_all = l2_normalise(teacher @ W)  # (N, 384)

    # ---- Datasets ----
    train_ds = TeacherTargetDataset(
        [texts[i] for i in train_idx], targets_all[train_idx]
    )
    eval_ds = TeacherTargetDataset(
        [texts[i] for i in eval_idx], targets_all[eval_idx]
    )

    # ---- Model ----
    tok = AutoTokenizer.from_pretrained(STUDENT_NAME)
    if args.resume:
        log.info("resuming from %s", args.resume)
        student = StudentEncoder(args.resume).to(device)
    else:
        student = StudentEncoder().to(device)

    # ---- Loader ----
    batch = args.batch
    train_dl = DataLoader(
        train_ds, batch_size=batch, shuffle=True, num_workers=0,
        collate_fn=collate(tok),
    )
    eval_dl = DataLoader(
        eval_ds, batch_size=batch, shuffle=False, num_workers=0,
        collate_fn=collate(tok),
    )

    # ---- Optim ----
    opt = torch.optim.AdamW(student.parameters(), lr=args.lr, weight_decay=0.01)
    n_step = math.ceil(len(train_idx) / batch) * args.epochs
    scheduler = torch.optim.lr_scheduler.LinearLR(
        opt, start_factor=1.0, end_factor=0.01, total_iters=n_step,
    )

    # ---- Train ----
    student.train()
    step = 0
    t0 = time.time()
    for ep in range(args.epochs):
        for enc, target in train_dl:
            enc = {k: v.to(device) for k, v in enc.items()}
            target = target.to(device)

            student_emb = student(**enc)  # (B, 384), L2-normed
            if args.phase == "b":
                student_emb_q = fake_quant_3bit(student_emb)
                mse_loss = F.mse_loss(student_emb, target)
                qat_loss = F.mse_loss(student_emb_q, target)

                # InfoNCE in-batch (target as positives, others as negatives)
                logits = student_emb @ target.t() / 0.05  # temp 0.05
                labels = torch.arange(logits.size(0), device=device)
                nce_loss = F.cross_entropy(logits, labels)

                loss = 1.0 * mse_loss + 0.3 * nce_loss + 0.2 * qat_loss
                parts = (mse_loss.item(), nce_loss.item(), qat_loss.item())
            else:
                loss = F.mse_loss(student_emb, target)
                parts = (loss.item(), 0.0, 0.0)

            opt.zero_grad()
            loss.backward()
            opt.step()
            scheduler.step()

            if step % 50 == 0:
                elapsed = time.time() - t0
                rate = (step + 1) / elapsed if elapsed > 0 else 0
                remaining = (n_step - step) / rate if rate > 0 else 0
                log.info(
                    "ep=%d step=%d/%d loss=%.4f mse=%.4f nce=%.4f qat=%.4f "
                    "lr=%.2e %.1f step/s ETA=%.1fmin",
                    ep, step, n_step, loss.item(), *parts,
                    scheduler.get_last_lr()[0], rate, remaining / 60,
                )
            step += 1

    # ---- Eval cosine to PCA-projected teacher ----
    student.eval()
    cos_sum, n = 0.0, 0
    with torch.no_grad():
        for enc, target in eval_dl:
            enc = {k: v.to(device) for k, v in enc.items()}
            target = target.to(device)
            s = student(**enc)
            cos = (s * target).sum(dim=1)
            cos_sum += cos.sum().item()
            n += s.size(0)
    mean_cos = cos_sum / max(n, 1)
    log.info("=== eval mean cosine: %.4f (gate ≥ 0.85) ===", mean_cos)

    # ---- Save ----
    out = MODELS_DIR / f"student_minilm_phase{args.phase.upper()}"
    out.mkdir(exist_ok=True, parents=True)
    student.backbone.save_pretrained(out)
    tok.save_pretrained(out)
    (out / "eval_cosine.txt").write_text(f"{mean_cos:.6f}\n")
    log.info("saved %s", out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("a", "b"), default="a")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--resume", default=None,
                    help="path to a saved student dir (required for phase b)")
    args = ap.parse_args()

    if args.phase == "b" and not args.resume:
        raise SystemExit("phase b requires --resume <phase-a checkpoint>")
    run(args)


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    main()
