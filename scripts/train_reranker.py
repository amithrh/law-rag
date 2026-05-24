#!/usr/bin/env python3
"""Stage 3 — fine-tune bge-reranker-v2-m3 on filtered SC triples.

Why this exists — the production reranker (BAAI/bge-reranker-v2-m3,
zero-shot) is currently the bottleneck for several failure modes
flagged in the 200-query eval:
  - 22% of usable answers cite SC caselaw only (no bare-act), even
    when the operative Act IS in the corpus and surfaces in top-32
  - The reranker scores SC paragraphs higher than bare-act sections
    on lay-phrase queries because SC paragraphs use lay-adjacent
    English while bare-act language is formal/legalese

The fine-tune teaches the reranker that when an SC paragraph cites
a bare-act section, the bare-act section is the MORE RELEVANT
target for retrieval — pushing bare-act chunks above SC paragraphs
in the rerank order.

Inputs (from Task #40 filter):
  data/training/splits/train.jsonl  (~2,331 triples)
  data/training/splits/eval.jsonl   (~223 triples)

Each triple becomes 2 training examples:
  (query, positive_text)        -> label 1.0
  (query, hard_negative_text)   -> label 0.0

Architecture (per Agent 2 subagent review):
  - sentence-transformers CrossEncoder (NOT raw HF Trainer)
  - Base: BAAI/bge-reranker-v2-m3 (568M params)
  - Stack: PyTorch + MPS (NOT MLX — MLX adapter immaturity)
  - Loss: BCEWithLogitsLoss (built into CrossEncoder)
  - Batch 16 directly (sentence-transformers fit() does not support
    grad-accum; we use larger batch instead. M4 Max 64GB unified
    memory handles batch 16 × max_len 512 × 568M params fine)
  - lr 2e-5, 2 epochs, max_len 512, FP16 autocast
  - AdamW, linear warmup 10% then linear decay

Wall budget: ~3.5h on M4 Max (was Agent 2's estimate at max_len 384;
we bumped to 512 to fit ~p90 positive_text length, expect +30% wall
= ~4.5h)

Output:
  models/bge-reranker-v2-m3-finetuned/  (checkpoint dir, swappable
                                          via reranker_model_path
                                          config A/B knob)

Gate (next step, NOT in this script):
  - AUC on held-out eval triples
  - 500-query realistic eval pass-rate ≥ baseline + 3pp
  - No regression on REFUSE_correct count

Usage:
  PYTHONPATH=. PYTORCH_ENABLE_MPS_FALLBACK=1 \\
      .venv/bin/python scripts/train_reranker.py

  # Smoke test (5 train examples, 1 epoch):
  PYTHONPATH=. PYTORCH_ENABLE_MPS_FALLBACK=1 \\
      .venv/bin/python scripts/train_reranker.py --smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from pathlib import Path

import torch

ROOT = Path(__file__).parent.parent
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("train_reranker")


def load_triples_as_examples(path: Path):
    """Each JSONL row -> two (query, doc, label) tuples for CrossEncoder."""
    from sentence_transformers import InputExample
    out: list[InputExample] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            q = d["query"]
            pos = d["positive_text"]
            neg = d["hard_negative_text"]
            out.append(InputExample(texts=[q, pos], label=1.0))
            out.append(InputExample(texts=[q, neg], label=0.0))
    return out


def build_evaluator(eval_examples, name: str):
    """Use BinaryClassificationEvaluator on the (q, doc, label) pairs.

    CrossEncoder fit() accepts an evaluator callable; the standard
    one for ranking-style supervision is CEBinaryClassificationEvaluator
    which reports AUC + accuracy.
    """
    from sentence_transformers.cross_encoder.evaluation import (
        CrossEncoderClassificationEvaluator,
    )
    sentence_pairs = [ex.texts for ex in eval_examples]
    labels = [int(ex.label) for ex in eval_examples]
    return CrossEncoderClassificationEvaluator(
        sentence_pairs=sentence_pairs,
        labels=labels,
        name=name,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-model", default="BAAI/bge-reranker-v2-m3")
    p.add_argument("--train", default="data/training/splits/train.jsonl")
    p.add_argument("--eval", default="data/training/splits/eval.jsonl")
    p.add_argument("--out", default="models/bge-reranker-v2-m3-finetuned")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max-len", type=int, default=512)
    p.add_argument("--warmup-frac", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="mps")
    p.add_argument("--fp16", action="store_true", default=True,
                   help="Use FP16 autocast (default on)")
    p.add_argument("--smoke", action="store_true",
                   help="Tiny subset, 1 epoch — quick wiring test")
    args = p.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    train_path = ROOT / args.train
    eval_path = ROOT / args.eval
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not train_path.exists():
        raise SystemExit(f"train file missing: {train_path}")
    if not eval_path.exists():
        raise SystemExit(f"eval file missing: {eval_path}")

    log.info("loading examples...")
    train_examples = load_triples_as_examples(train_path)
    eval_examples = load_triples_as_examples(eval_path)
    log.info("  train examples: %d (from %d triples)",
             len(train_examples), len(train_examples) // 2)
    log.info("  eval  examples: %d (from %d triples)",
             len(eval_examples), len(eval_examples) // 2)

    if args.smoke:
        train_examples = train_examples[:20]
        eval_examples = eval_examples[:10]
        args.epochs = 1
        log.warning("SMOKE MODE — using tiny subset")

    log.info("device: %s", args.device)
    log.info("base model: %s", args.base_model)
    log.info("max_len: %d  batch_size: %d",
             args.max_len, args.batch_size)
    log.info("epochs: %d  lr: %g  warmup_frac: %.2f",
             args.epochs, args.lr, args.warmup_frac)

    # Import here so script entry is fast even if deps slow to import
    from sentence_transformers import CrossEncoder
    from torch.utils.data import DataLoader

    model = CrossEncoder(
        args.base_model,
        num_labels=1,
        max_length=args.max_len,
        device=args.device,
    )

    train_loader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=args.batch_size,
    )

    evaluator = build_evaluator(eval_examples, name="sc_triples_eval")

    steps_per_epoch = max(1, len(train_loader))
    total_steps = steps_per_epoch * args.epochs
    warmup_steps = int(total_steps * args.warmup_frac)
    log.info("steps/epoch: %d  total_steps: %d  warmup: %d",
             steps_per_epoch, total_steps, warmup_steps)

    t0 = time.time()
    log.info("starting fit...")
    model.fit(
        train_dataloader=train_loader,
        evaluator=evaluator,
        evaluation_steps=max(1, steps_per_epoch // 2),  # eval mid-epoch
        epochs=args.epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": args.lr},
        weight_decay=0.01,
        output_path=str(out_path),
        use_amp=args.fp16,
        save_best_model=True,
        show_progress_bar=True,
    )
    elapsed = time.time() - t0
    log.info("DONE in %.1f min", elapsed / 60)
    log.info("saved to: %s", out_path)

    # Final eval on held-out
    log.info("final eval on held-out triples...")
    final_score = evaluator(model, output_path=str(out_path / "eval_final"))
    # CrossEncoderClassificationEvaluator in ST 5.x returns a dict
    if isinstance(final_score, dict):
        for k, v in final_score.items():
            log.info("  %s: %s", k,
                     (f"{v:.4f}" if isinstance(v, (int, float)) else v))
    else:
        log.info("final score: %s", final_score)


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    main()
