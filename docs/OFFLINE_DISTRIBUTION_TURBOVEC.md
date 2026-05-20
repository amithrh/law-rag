# Offline distribution via TurboVec — design doc

**Status:** plan locked, gated on stage-4 distillation
**Author:** session @ 2026-05-21
**Owner:** retrieval/distribution track

## Goal

Ship the Indian-law RAG as a **single ~400 MB zip** that runs on any
laptop with no internet, no Postgres, no Ollama. Targets:

- DLSA district legal-aid offices (intermittent connectivity)
- Paralegals doing intake on phones / cheap laptops
- Bar council reading rooms
- Disaster-relief legal aid (cyclone districts, etc.)

The server (NALSA web app) stays on full Postgres + pgvector + LLM and
delivers higher-quality answers when internet is available. The offline
bundle is the **fallback delivery surface** with the same trained models
underneath.

## Why TurboVec, not pgvector-offline / other options

| Option | Verdict |
|---|---|
| Ship Postgres + pgvector as a docker image | ~5 GB image, requires Docker, not laptop-friendly |
| Ship SQLite with raw FP16 BLOB column | ~1 GB just for embeddings; no quantization wins |
| Use FAISS / Annoy / HNSWlib + pickle | C extensions hard to deploy across platforms; no SQLite integration |
| **TurboVec (this plan)** | **single SQLite file, native quantization, MIT license, ours** |

TurboVec is purpose-built for this: SQLite-backed vector store with
3-bit rotated scalar quantization. Owned codebase (we can patch what we
need). Already supports the metadata / source-quality features we'd
want for legal use.

## The spike that motivated this doc

On 2026-05-21 we ran a quality spike: mirrored the 11,420 bare-act
chunks (1024-d bge-m3 FP16) into TurboVec at 3-bit, ran 12 representative
queries through both stores, measured overlap.

**Headline result — 1024-d on raw bge-m3 is NOT ready for offline today:**

| Metric | TurboVec 3-bit (1024-d raw) |
|---|---:|
| Mean recall@20 vs pgvector | 69% |
| Mean recall@3 | 64% |
| Top-1 exact match | 50% (6/12) |
| Section-level recall@5 (treating sub-chunks as equivalent) | 48% |
| Size: 11.4K chunks | 5.2 MB (4.5× compression) |

Spike scripts kept under `scripts/`:
- `scripts/build_turbovec_mirror.py` — mirrors a Postgres source into TurboVec
- `scripts/eval_turbovec_vs_pgvector.py` — overlap + section-level recall measurement

3-bit, 4-bit, and 3-bit+QJL all converged at ~68% — bit budget is not
the bottleneck. The TurboQuant codebook assumes a uniform-on-the-sphere
input distribution which bge-m3 at 1024-d does not satisfy.

**Diagnosis:** bge-m3 1024-d is anisotropic (a few "hot" dimensions
carry most of the signal). Rotated scalar quantization can't fix the
underlying distribution.

## What makes TurboVec actually work for us

Two changes between today and the offline ship:

### 1. Distill bge-m3 → 384-d (stage 4 of training plan)

Training plan stage 4 is to distill bge-m3 to a smaller embedder. We
were going to do this anyway for laptop deployment. Key choices:

- Output dim: **384-d** (TurboVec ships a tuned 384-d codebook out of
  the box; smaller models fit on phones)
- ~50M params (vs bge-m3's 568M)
- ONNX export for portability

### 2. Quantization-aware fine-tuning

Train with simulated 3-bit quantization in the forward pass so the
student learns a quantization-friendly embedding space. Loss term added
during stage 4:

```
total_loss = teacher_kd_loss + alpha * triplet_loss + beta * QAT_loss
```

This is standard (PQ-aware training, product-quantization-friendly
embeddings). No research needed.

### Predicted post-distillation numbers

| | 1024-d raw (spike) | 384-d distilled + QAT (target) |
|---|---:|---:|
| Section-level recall@5 vs server | 48% | **>85%** |
| Bundle size: full 484K corpus | 186 MB | **~72 MB** (vectors only) |
| Total ship size with text+models | n/a | **~400 MB** |
| Per-query latency on M1 laptop CPU | n/a | ~30-80ms |

If we don't hit ≥85% section recall, the offline track stays in beta
and we ship server-only. The gold eval (stage 1) is what tells us.

## Architecture

```
              ┌───────────────────────────────────────┐
              │   POSTGRES + PGVECTOR (server)        │
              │   Full hybrid retrieval               │
              │   bge-m3 1024-d, sparse, BM25         │
              │   qwen3:14b LLM, full verifier        │
              │   Latency: ~40s, Quality: 79%/64% OK  │
              └───────────────────────────────────────┘
                              ▲
                              │ same trained components
                              │ (distilled in stage 4)
                              ▼
              ┌───────────────────────────────────────┐
              │   TURBOVEC OFFLINE BUNDLE             │
              │                                       │
              │   lawrag.db (~250 MB)                 │
              │   ├─ chunks table (text + metadata)   │
              │   ├─ embeddings (384-d × 484K × 3-bit)│
              │   └─ codebook, rotation matrix        │
              │                                       │
              │   models/                             │
              │   ├─ embedder.onnx (~95 MB)           │
              │   └─ reranker.onnx (~55 MB)           │
              │                                       │
              │   client.py (~100 lines)              │
              │                                       │
              │   Latency: ~80ms, Quality: target 85% │
              └───────────────────────────────────────┘
```

## The offline client (sketch)

```python
# scripts/lawrag_offline_client.py
import onnxruntime as ort
import turbovec

embedder = ort.InferenceSession("models/embedder.onnx")
reranker = ort.InferenceSession("models/reranker.onnx")
db = turbovec.connect("lawrag.db")

def ask(query: str, top_k: int = 5):
    qv = encode(embedder, query)
    candidates = db.search("chunks", qv, top_k=50,
                           metadata_filter={"source_type": "bare_act"})
    reranked = rerank(reranker, query, candidates)
    return reranked[:top_k]
```

That's the full offline retrieval surface. No internet, no Postgres,
no LLM, no Ollama. Just shows the user the bare-Act text + landmark SC
case snippets, with anchors that double-click to the original PDFs (also
bundled).

For lawyers who want LLM-generated prose answers: use the server. The
offline bundle is **retrieval + citation snippets only** — which is
already 70-80% of the value for a legal-aid intake desk.

## Sequence of work

| Stage | Action | When | Output |
|---|---|---|---|
| 4a (training plan) | distill bge-m3 → 384-d QAT | week 3-4 | `bge-distilled-384.onnx` |
| 4b | distill bge-reranker | week 4 | `reranker-distilled.onnx` |
| 5 | re-embed 484K chunks @ 384-d | week 4 (~1 hr) | staging table |
| 6 | build TurboVec bundle | week 5 | `lawrag-offline.db` |
| 7 | offline client + eval | week 5 | shippable zip |

Gates:
- Section-level recall@5 ≥ 85% on the 200-query gold set
- Latency p50 ≤ 100ms on a base M1 MacBook
- Bundle size ≤ 500 MB
- Works on Python 3.10+ with onnxruntime-cpu only (no GPU required)

## What we are NOT doing

- Not replacing the server's pgvector with TurboVec. Server keeps
  hybrid retrieval + full-precision FP16 + HNSW.
- Not shipping TurboVec at 1024-d. The spike confirms it's not ready
  at this dim, regardless of bit budget.
- Not training the embedder specifically for TurboVec. Stage 4
  distillation has many uses (laptop deploy, phone deploy, faster
  inference); QAT is just one term in its loss.
- Not committing to TurboVec if it fails the gate. If section recall
  on the gold set is <80%, we either (a) bump dim to 512-d, (b) drop
  to 5-bit, or (c) ship offline-mode with raw FP16 (larger file).

## Why this is the right architectural call

1. **One trained model serves two surfaces.** Distillation is in the
   training plan anyway.
2. **The offline bundle solves a real distribution problem.** DLSA
   offices don't have reliable internet. NALSA reach is gated by
   connectivity, not by NALSA's will.
3. **Failure modes are independent.** Server can go down without
   affecting offline. Offline can be wrong (rare query) without
   affecting server.
4. **TurboVec is a project the team controls.** When we hit an
   integration friction (no 1024-d codebook, etc.), we can patch
   upstream.

## References

- Spike measurement: `scripts/eval_turbovec_vs_pgvector.py`
- TurboQuant paper: arXiv:2504.19874
- QJL paper: arXiv:2406.03482
- TurboVec source: github.com/amithrh/turbovec (private)
