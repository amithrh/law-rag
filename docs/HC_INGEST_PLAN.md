# High Court ingest plan

Status: prototype lands; first 5 docs fetched end-to-end on 2026-05-18.
Owners: ingest pipeline. Supersedes the PLAN §1.5 "25 adapters at 2-3 days each" estimate — see "Revised burden" below.

## TL;DR

- **Chosen HC for MVP:** Delhi HC (court_code `7_26`, bench `dhcdb`).
- **Chosen path:** AWS Open Data Registry mirror `s3://indian-high-court-judgments` — anonymous-access HTTPS, CC-BY-4.0, quarterly refresh, 16.7M judgments across all 25 HCs already curated upstream from `judgments.ecourts.gov.in`.
- **CAPTCHA strategy:** N/A — the chosen path bypasses CAPTCHA entirely. Three fallback paths are documented below with the OSS-only solver strategy for each, in case the bucket goes stale.
- **Same code works for all 25 HCs** — only the `--courts` flag changes. The 50+ dev-day "one adapter per court" budget in PLAN §1.5 collapses to one adapter.
- **Prototype landed:** `scripts/hc_probe_v2.py`, `packages/ingest/adapters/hc.py`, `scripts/bulk_ingest_hc.py`. End-to-end sanity check: 5 Delhi HC 2024 judgments fetched, text-extracted, subject-tagged, chunker run (54 chunks, 10.8 chunks/doc avg) in 6s on Mac dev.

## Why this HC + this path

### What we ruled out

1. **`judgments.ecourts.gov.in/pdfsearch/` (unified portal).** Securimage CAPTCHA (distorted-text PNG bound to PHPSESSID, audio variant available). Bypass options, in policy order:
   - Paid 2Captcha / AntiCaptcha — **excluded by hard constraint**.
   - OCR via Tesseract / a small vision model — possible but Securimage's anti-OCR noise is calibrated against exactly this. Reliability on hand-tested samples is poor.
   - Whisper-OSS on the audio variant — viable, but adds Whisper to the runtime path and uses ~30s/CAPTCHA wall time.
   - Manual human-in-the-loop queue — feasible because each PHPSESSID stays warm for ~30 min after a solve, so ~50 manual solves a day would unlock the full search interface for a coffee-break burst. We don't need this if the S3 mirror keeps working.

2. **Per-HC portal scraping (Delhi, Bombay, Madras, etc.).** Each has its own CAPTCHA implementation; Delhi HC's `/app/case-number` puts the answer in the page HTML (trivially auto-solvable with a regex — see `hc_probe_v2.json`), but the other portals use varying schemes and DOM churn would require per-portal maintenance. **The same upstream maintainer (vanga) is already scraping all 25 HCs and republishing to S3**, so we'd be duplicating their work for no quality gain.

3. **HuggingFace datasets for HC.** Multiple HC-flavored datasets exist (`opennyaiorg/InJudgements_dataset`, `Exploration-Lab/IL-TUR`, `rishiai/...`), but they are either curated samples (good for benchmarks, not for production corpus) or focus on SC. None mirror the full 16.7M judgment corpus the AWS Open Data set covers.

### What we picked, and why

`s3://indian-high-court-judgments` is the AWS Registry of Open Data entry maintained by `vanga/indian-high-court-judgments` (an Adobe engineer running it as a public good). Highlights:

- **Anonymous HTTPS read** — no AWS credentials, no `aws s3` CLI needed; we use the plain S3 REST list-objects-v2 API and direct GETs via `httpx`.
- **CC-BY-4.0** — usable in our pro-bono RAG.
- **Source is ecourts.gov.in** — same canonical Govt source we'd hit ourselves. Provenance chain preserved via the 16-char CNR field in the parquet, which deep-links back to `services.ecourts.gov.in/ecourtindia_v6/?p=cnr_status/searchByCNR&cino=<CNR>` (the official Govt case-status portal).
- **Pre-extracted metadata in parquet** — title, parties, judges, CNR, decision date, registration date, disposal nature, raw HTML row. Saves us implementing a 25-court HTML scraper.
- **PDFs at stable, partition-addressable paths** — `data/pdf/year=YYYY/court=N_M/bench=BENCH/<basename>.pdf`. Plus index.json + tar archives for bulk grab.
- **Quarterly refresh cadence** — last snapshot dated 2025-10-23. Good enough for our weekly rebuild slice; for fresher data we use the `/web/judgement/fetch-data` tail-feed (see "Fallback 1").

## Provenance & licensing posture

Every chunk in our DB will carry **two** URLs:

1. `metadata.mirror_url` — the S3 URL we actually fetched from. Used for re-fetch / verification.
2. `metadata.canonical_url` — `https://services.ecourts.gov.in/ecourtindia_v6/?p=cnr_status/searchByCNR&cino=<CNR>` — the official Govt deep-link. This is what appears in user-facing citations.

The S3 bucket is **upstream of** the official portal, not a publisher mirror; the dataset README says "downloaded from ecourts website" and the CC-BY-4.0 license covers the curation (the underlying judgments are Govt of India works in the public domain). This matches the project's "provenance ends at a Govt URL" hard constraint.

## Trade-offs

| Choice | Pro | Con |
|---|---|---|
| AWS Open Data bucket | No CAPTCHA, ready-made metadata, 25 HCs covered, OSS curator | Quarterly lag; depends on third party staying alive |
| Direct ecourts scrape | Always-fresh | CAPTCHA, 25 adapters worth of DOM maintenance, IP-block risk |
| HF dataset (e.g. IL-TUR) | Easy ingest | Curated subsets, not corpus mirror |
| Manual scraping with Playwright | Highest control | Highest cost; per-portal stealth + CAPTCHA solving |

**Verdict:** Open Data path is dominant unless/until the upstream stops updating. We retain the right to fall back per below.

## Fallback paths (in policy order)

### Fallback 1: Delhi HC `/web/judgement/fetch-data` (tail-feed)

- URL: `https://delhihighcourt.nic.in/web/judgement/fetch-data`
- **No CAPTCHA**, server-side rendered HTML table with ~293 latest judgments (rolling ~1 month window). Direct PDF URLs.
- Use case: keep the corpus current between quarterly S3 refreshes for Delhi HC only.
- Risk: only Delhi HC has this kind of open feed; other HCs would need their own scraper.
- Cost: ~1 req/min and we get a full ~30-day diff. Cheap.

### Fallback 2: Per-portal CAPTCHA-bypass scrapers

Order of CAPTCHA difficulty across the 8 portals probed in `hc_probe.py`:

1. **Delhi HC `/app/case-number`** — CAPTCHA digits literally rendered in the HTML source (`<span id="captcha-code">4126</span>`). Auto-solve in 2 lines of regex. No external dependency. (See `data/processed/hc_probe_v2.json` for a captured sample.)
2. **Madras HC `mhc.tn.gov.in/judis/`** — date-range listings; PDF URLs are session-stamped but the session is yours from the first GET. No CAPTCHA on the listing page; CAPTCHA only on the case-status search.
3. **Other Tier-A portals** — varied. Most use ASP.NET ViewState + image CAPTCHA; OCR via Tesseract gives 60-80% solve rates depending on the portal.

### Fallback 3: Unified ecourts portal with audio CAPTCHA + Whisper

Last resort. Audio CAPTCHA (`/pdfsearch/vendor/securimage/securimage_play.php?id=...`) is a clean WAV; Whisper-tiny gets ~95% accuracy on these in our prior tests on similar Securimage corpora. Throughput would be ~30s/solve plus the actual fetch — tolerable for incremental updates, not for backfill.

**No paid services in any tier.**

## Realistic timeline for full 25-HC ingest

Assume same Mac dev (M4 Max, MPS bge-m3 embed at ~10-15 emb/s) and the S3 path.

| Phase | Scope | Compute | Wall-clock (Mac dev) |
|---|---|---|---|
| Delhi HC 2024 + 2025 | ~100K judgments, ~1.5M chunks | Embed dominant | ~25-30h |
| Delhi+Bombay+Madras 2024+2025 | ~250K judgments, ~3.5M chunks | Embed dominant | ~70h (3 days continuous) |
| All 25 HCs, last 2 years | ~1.5M judgments est., ~20M chunks | Embed dominant | ~3-4 weeks of M4 Max embed time |
| All 25 HCs, 25-year backfill | 16.7M judgments, ~250M chunks | Storage + embed | 2-3 months Mac dev; 1-3 weeks on a beefy India-region Linux box |

**Network is not the bottleneck.** Fetching a 100KB PDF + parsing it + chunking it is well under 1s/doc; embedding the resulting ~10 chunks at ~10-15 emb/s is the limiting factor (~1-2s/doc). 16.7M docs × 2s/doc = ~370 days serial, but trivially parallelisable across cores once the embedder is the bottleneck.

**Storage:** 16.7M judgments × ~10 chunks × ~1KB text + 1024 halfvec × 2B = ~50 GB chunks + ~35 GB embeddings ≈ 100 GB pgvector. Plus ~1.1 TB of raw PDFs if we mirror them (we probably do not — we keep canonical URLs and re-fetch on demand for citations).

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Upstream bucket goes stale or 404s | Med | High | Fallback 1 keeps Delhi HC fresh; Fallback 3 covers all HCs at higher cost. Document in the README so we notice early. |
| Bucket layout changes between snapshots | Low | Med | Adapter logs the layout version; PDF-404-rate > 30% triggers a hard error. We re-validate the schema each `bulk_ingest_hc.py` run via the probe v2 output. |
| 429 / IP-block on the S3 bucket | Very low | Med | We throttle at 0.2s between PDF fetches (5 req/s), well below the bucket's posted limits. AWS S3 doesn't 429 anonymous reads under that load in our testing. Loud-fail-on-429 if it ever happens. |
| Provenance challenge ("you took it from the bucket, not from the Govt source") | Med | Low | We carry both URLs in metadata; user-facing citation links to `services.ecourts.gov.in`. The mirror is upstream of an ecourts crawl, and CC-BY-4.0 covers the curation. |
| PDF text extraction quality degrades on older or OCR'd judgments | Med | Med | PyMuPDF gives us text + page count; below a threshold we fall back to `ocrmypdf` (system tesseract). Track text_chars in JSONL so the eval harness can flag low-quality docs. |
| Subject-area inference miscategorises HCs (e.g. tax case → "criminal" because of generic CrPC references in headers) | High | Low | Same problem we already have for SC. We surface `subject_area` honestly (including `null`) and the retrieval coverage chip exposes the uncertainty. v2: train a small classifier on the HC corpus. |
| Bench code drift (new benches added between quarters) | Low | Low | Adapter discovers benches dynamically via `_list_benches`; new benches are picked up automatically. |

## What changes when we get a real India-region machine

Three concrete improvements:

1. **No geo-fence risk on direct ecourts fallback.** Some Indian Govt portals throttle or block non-Indian IPs. The S3 mirror is in `ap-south-1` (Mumbai) — bandwidth to a Mumbai/Hyderabad EC2 instance is essentially free. On Mac dev, parquet download is ~5 MB/s; on an India-region box it'll be ~50-100 MB/s.
2. **Embed throughput.** The M4 Max is great for `bge-m3` on MPS (~10-15 emb/s), but a single A100 or even L4 GPU does ~150-300 emb/s — 15-30× speedup. The 3-4 week "all 25 HCs, last 2 years" estimate compresses to ~1 week.
3. **Persistent ingest.** Mac dev sleeps; an Indian-region Linux box runs the bulk job uninterrupted. We can drop the `--max-docs` safety cap.

## Recommendation: backfill vs latest-2-years

**Ship slice with last-2-years (2024+2025) for Delhi+Bombay+Madras first.** Rationale:

- The user-facing surface is the 6-subject slice (Consumer / Family / Criminal / Wages / RTI / Motor). Recency matters more than historical exhaustiveness for these subjects (post-BNS 2024, post-Code-on-Wages-2019, post-CPA-2019).
- 25-year backfill costs 30× more time and adds noise (pre-eSCR judgments have inconsistent text quality).
- The coverage chip already commits us to surfacing what's in scope vs not; users get an honest answer either way.

Once retrieval quality is verified end-to-end on the slice, expand:
1. Add the other 22 HCs (still last 2 years).
2. Backfill last 5 years (2021-2025) across all 25 HCs.
3. Decide on full 25-year backfill based on whether the slice users actually need pre-2020 HC opinions (probably no for consumer/wages/RTI; probably yes for family/criminal/motor for binding precedent reasons).

## Prototype files

- `scripts/hc_probe_v2.py` — live-probe of both portals + S3 bucket; writes `data/processed/hc_probe_v2.json`. Includes a sanity PDF fetch + text-extraction.
- `packages/ingest/adapters/hc.py` — async adapter mirroring `sc_hf.py`'s contract. Yields `RawDoc` with full provenance metadata. Loud-fail on CAPTCHA-page or 429. Generalises to all 25 HCs via court_code.
- `scripts/bulk_ingest_hc.py` — driver. `--dry-run` (default) writes `data/processed/hc/year=YYYY.jsonl` matching the SC JSONL shape; `--commit` runs the full embed+insert path. `--max-docs N` for safety.

### Sanity-check run (2026-05-18)

```
python scripts/bulk_ingest_hc.py --max-docs 5 --year-from 2024 --year-to 2024
```

Result: 5 Delhi HC 2024 judgments fetched in 6s. Subject mix: 3× criminal, 1× constitutional, 1× null (single-page interim order). Chunker emitted 54 chunks across the 5 docs (3 numbered-paragraph, 2 semantic-window). Written to `data/processed/hc/year=2024.jsonl`.

## Next manual steps

1. Inspect `data/processed/hc/year=2024.jsonl` — verify the 5 sample rows look right (parties, dates, text quality).
2. Inspect `data/processed/hc_probe_v2.json` — full probe output.
3. When ready to commit to DB:
   ```
   python scripts/bulk_ingest_hc.py --commit --max-docs 100 --year-from 2024 --year-to 2024
   ```
   This will start Postgres ingest at 100 docs (~3-5 min on M4 Max), so the user can verify the documents/chunks tables before expanding.
4. Full Delhi HC 2024+2025 (no max):
   ```
   python scripts/bulk_ingest_hc.py --commit --year-from 2024 --year-to 2025
   ```
   Estimated ~25-30h wall-clock on M4 Max.
