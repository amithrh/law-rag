# Open Questions — Decisions the plan defers

Companion to `PLAN.md`. Each question is a decision the plan cannot make on paper.

- **Day 0 / Day 1 (before downstream choices lock in):** Q1, Q2, Q3, Q4, Q6, Q7, Q8
- **Post-slice (after we have eval signal and real query traffic):** Q5
- **Human-input, no bench:** Q9 (needed before §4.3 strictness and §10.2 PII bar are finalized)

Resolve each before the design choice locks in, then update the relevant section of `PLAN.md` and delete the entry here.

---

## Q1 — Verifier topology: parallel-with-generation vs batched-after-stream

**Plan section:** §4.3

**Question:** Can the parallel-verifier topology (LLM keeps generating into a buffer while NLI runs on the previous sentence) actually hide verifier latency from the user, or does it stall in practice because LLM and NLI compete for the same MPS / CPU?

**Decide with:**
- Bench bge-reranker-v2-m3 (or chosen NLI checkpoint) on M2/M3 Pro MPS:
  - single-sentence single-citation: p50 / p95
  - single-sentence multi-citation (3 cited passages averaged): p50 / p95
  - batch of 8 sentences: p50 / p95 per sentence
- Bench llama3.1:8b TTFT and per-token latency on Ollama, idle vs. with NLI running concurrently.
- Watch for memory pressure (Ollama 8B + NLI model both resident on a 32 GB Mac).

**Decision rule:**
- If single-sentence NLI p95 ≤ 200 ms and concurrent run doesn't degrade LLM throughput >20% → ship the parallel topology.
- Otherwise → ship batched-after-stream verification (server-side hold + single batch verify + stream only if skip ratio acceptable). Document as v1 default; parallel becomes v1.5.

---

## Q2 — Postgres HNSW partition fanout vs. single un-partitioned index

**Plan section:** §5.4

**Question:** When the query needs to span SC + acts + circulars (which is the *normal* case for a legal question, not the edge), does fanning out across 4 per-partition HNSW indexes multiply p95 unacceptably?

**Decide with:**
- Build a 1M-chunk seed split four ways (SC ~600K / acts ~200K / circulars ~150K / HC sample ~50K).
- Also build a **synthetic 3M proxy**: duplicate the 1M seed 3× with disambiguated chunk IDs (and slightly perturbed embeddings — add ε~N(0, 0.001) — so HNSW doesn't collapse on dupes). Not perfect, but the only way to test scaling without waiting on the full ingest.
- Bench three topologies on the same 50-query workload, at both 1M and 3M:
  1. **Single un-partitioned HNSW** on `chunks` with `source_type` as a btree filter (pre-filter via WHERE then HNSW search, or HNSW then post-filter — bench both).
  2. **Partitioned table with per-partition HNSW** (alternative), parallel UNION across partitions.
  3. **Per-source Qdrant collections**, app-side merge + rerank.
- Metrics: p50 / p95 latency, recall@10 vs brute force, query-plan readability.
- **Extrapolation:** HNSW search cost is approximately log-linear in N at fixed `ef_search`. Plot p95 at 1M and 3M, fit log-linear, project to 5M and 10M. Decision rule applies to the *projected* p95, not the measured 1M number alone.

**Decision rule:**
- If single un-partitioned + filter's projected p95 at 5M stays within budget → keep pgvector default, drop partitioning entirely (plan §5.4 already defaults to this).
- If partitioned + UNION stays within budget but un-partitioned doesn't → switch §5.4 default back to partitioned.
- If neither holds at 5M projection → migrate to Qdrant *before* schema is built around Postgres (§5.1 budgets 1–2 weeks of migration).

**Why this matters now:** §5.4 currently defaults to un-partitioned (single table + filter). The schema in §9 matches. If the bench inverts this assumption, both sections need updating before Day 2.

---

## Q3 — bge-m3 embedding throughput on Mac MPS

**Plan section:** §9 Days 6–7 (1M-chunk embedding target)

**Question:** How long does one full-corpus embedding pass actually take? The plan assumes 1M chunks ingest + index inside Days 6–7. If a single pass is 8+ hours and 2–3 passes are needed (after chunker fixes), this alone breaks the sprint.

**Decide with:**
- Bench bge-m3 on TEI on Mac MPS at three batch sizes (8 / 32 / 128) and three sequence lengths (256 / 512 / 1024 tokens).
- Throughput in chunks/sec. Memory pressure. Whether TEI on Mac is meaningfully different from running the model directly via `sentence-transformers`.
- If TEI is slow on Mac (it's mostly designed for CUDA), benchmark a direct `sentence-transformers` worker as a fallback.

**Decision rule:**
- If full-pass cost exceeds 4 hours → narrow the slice further. Drop SEBI from slice or use only last 3 SC years instead of 5.
- If 1.5–4 hours → keep slice, schedule embedding overnight on Day 5/6.
- If <1.5 hours → original plan stands.

---

## Q4 — Reranker batch latency on MPS

**Plan section:** §5.3

**Question:** What's the real cost of `bge-reranker-v2-m3` batch-of-50 on Mac MPS? The original draft asserted 200 ms; this is unverified. Reranker latency is on the critical path of every query.

**Decide with:**
- Bench batch sizes 10 / 25 / 50 / 100 on MPS.
- Sequence length variants (chunk text typically 512–1024 tokens).
- Compare against CPU baseline (fp32 / int8).

**Decision rule:**
- If batch-50 p95 > 500 ms → reduce rerank-K from 200 to 50–80; accept some recall hit.
- If batch-50 p95 < 250 ms → keep current plan.

---

## Q5 — Does bge-m3 sparse head actually beat BM25 on legal text? (POST-SLICE)

**Plan section:** §2.1, §2.3

**Question:** §2.1 reserves a schema column for the bge-m3 sparse head as a v1.5 retrieval signal. But does it actually lift recall on legal queries vs. plain BM25 — enough to justify the storage + scoring complexity?

**Decide with:**
- After v1 slice ships and we have a 50–100 query golden set:
  - retrieval-only ablation: BM25 alone vs. BM25 + sparse vs. dense alone vs. dense + sparse vs. all-three.
  - Per-query-type breakdown (statutory-section lookup vs. case-name vs. concept).
  - Report recall@10 and recall@20.

**Decision rule:**
- If sparse adds ≥3 pp recall@10 on statutory-lookup queries → ship in v1.5.
- If <1 pp → don't bother; remove the reserved column.
- 1–3 pp → judgment call based on storage cost.

---

## Q6 — IndiaCode OAI-PMH actually responds? — **RESOLVED 2026-05-17: NO**

**Plan section:** §1.3

**Result:** `curl https://www.indiacode.nic.in/oai/request?verb=Identify` returns HTTP 404 with a generic 500/404 HTML page. OAI-PMH is not exposed on this DSpace instance.

**Action taken:** IndiaCode adapter falls back to handle-page crawling (`/handle/123456789/<id>` enumerated via `/browse?type=actyear`). Update §1.3 to remove the optimistic OAI-PMH primary path.

---

## Q7 — eSCR view-page URL pattern stable without session cookies? — **PARTIALLY RESOLVED 2026-05-17**

**Plan section:** §1.1

**Result of network probe (2026-05-17):**
- `digiscr.sci.gov.in` returns **NXDOMAIN from public DNS resolvers (Google 8.8.8.8, Cloudflare 1.1.1.1)** — the host does not resolve outside Indian DNS. The SCI homepage at `sci.gov.in` *does* link to `https://digiscr.sci.gov.in/`, so it is a real subdomain — likely geo-fenced DNS or India-only DNS resolution. The user in India should test cold-fetch directly.
- `main.sci.gov.in` resolves (164.100.229.147) but connection times out from this network — likely IP-geofenced or firewall-restricted to Indian IPs.
- **Alternatives that ARE reachable from this network:**
  - `https://scr.sci.gov.in/scrsearch/` — HTTP 200 (Supreme Court Reports search). 22 KB landing page.
  - `https://judgments.ecourts.gov.in/KBJ/` — HTTP 200 (eCourts unified judgment portal). 13 KB landing page.
  - Internet Archive snapshots of `digiscr.sci.gov.in` exist (HTTP 200 on `web.archive.org`).

**Action taken:** §1.1 adapter strategy expanded to multi-host fallback (digiscr → scr.sci.gov.in → judgments.ecourts.gov.in → Internet Archive → HF Rahul1872). Cold-fetch behavior of the actual `digiscr` host remains untested; user must run the probe from an Indian IP, or production crawler must run on India-region infra.

**Still pending:** the actual cold-fetch behavior (CSRF token / session-cookie requirement) on `digiscr.sci.gov.in`. Has to be tested from India or via an India-region VPS.

---

## Q8 — HF dataset names + provenance — **PARTIALLY RESOLVED 2026-05-17**

**Plan section:** §1.1 fallback, §10.1

**Result of existence check (HTTP HEAD on HF API):**
- `opennyaiorg/InJudgments-SC` → **does not exist.** OpenNyAI's actual datasets: `aalap_instruction_dataset`, `aibe_dataset`, `InLegalNER`. None are an SC corpus.
- `ai4bharat/IndicLegalQA` → **does not exist.** ai4bharat has 30 datasets, none legal — they focus on Indic NLP (translation, NER, ASR, etc.).
- `Exploration-Lab/IL-TUR` → exists (HTTP 200) but is a benchmark, not a corpus.
- `law-ai/InLegalBERT-corpus` → **does not exist.** The model exists; the corpus is not separately released.

**Real candidates discovered:**
- **`Rahul1872/Indian-Supreme-Court-Judgments`** — CC-BY-4.0, 10K–100K rows, year-partitioned 1950–2025 (76 years), English + regional separated, full text in parquet + raw PDFs in tar. **Most promising SC source.** 1029 downloads.
- **`labofsahil/Indian-Supreme-Court-Judgments`** — CC-BY-4.0, 1002 sibling files. Identical file count to Rahul1872 — strong signal one is a fork. Treat as backup mirror.
- **`Immanuel30303/Indian-High-Court-Judgments-all`** — CC-BY-4.0, 1M–10M rows, year-partitioned parquet 1950+. **Most promising HC source covering Tier-A and beyond.**
- **`vihaannnn/Indian-Supreme-Court-Judgements-Chunked`** — MIT, 10K–100K, 2036 downloads. Pre-chunked; useful comparison baseline but provenance uncertain.
- **`KanoonGPT/indian-case-laws`** — Apache-2.0, 10M–100M rows. **Likely IndianKanoon-sourced** (name + structure). Exclude per §10.1 / no-paid-aggregators constraint.

**Still pending (Day-1 work, not Day-0):**
- 50-doc provenance sample per §10.1 on each candidate to verify they are court-issued text and not SCC/AIR/IndianKanoon headnote-formatted.
- Decision: Rahul1872 or labofsahil for SC, Immanuel30303 for HC, both pending provenance pass.

**Action taken:** Update §1.1 fallback list to drop the imaginary datasets and add the real CC-BY-4.0 candidates with the explicit caveat that provenance is unverified.

---

## Q9 — Deeper goal: who is the end user?

**Plan section:** the whole plan

**Question (for the human, not bench):** is this for practicing lawyers, researchers, students, public users, or a specific firm? The answer changes:
- Always-strict vs softened-strict threshold (§4.3).
- Whether PII is a release blocker (§10.2) or a "we'll get to it" item.
- Whether `/similar` is high-value (lawyers) or skippable (researchers).
- Whether coverage gaps are surfaced gently or aggressively (§4.4 coverage chip).
- Whether multi-tenancy / auth / audit-log matter at all.

Currently the plan assumes "research-use, non-commercial, local-first." If that's wrong, several decisions need re-tuning.

**Decision needed before:** finalizing §4.3 strictness threshold (30% skip-ratio default may move to 5% or 50%), §10.2 PII bar timing (release-gate may need to be in slice not post-slice), §4.4 coverage chip phrasing, and any auth / multi-tenancy work.

**Owner:** human (Amit).
