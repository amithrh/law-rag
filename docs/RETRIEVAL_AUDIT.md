# Retrieval audit — recall@20 vs hand-labeled gold passages

Run: 2026-05-19. Stack: bge-m3 dense + Postgres BM25 fusion (70/30) + bge-reranker-v2-m3 cross-encoder. Corpus: 16,158 SC judgments + 11 statutes. Method: `scripts/audit_retrieval_recall.py`.

## Headline

**recall@20 = 53% · recall@8 = 40% · recall@3 = 20%**

Decision rule per the architecture-research roadmap:

| recall@20 | verdict |
|---|---|
| ≥ 85% | retrieval is fine; verifier/prompt next |
| 65-85% | both retrieval and verifier need work; bge-m3 multi-head next |
| **< 65%** | **retrieval is the bottleneck; multi-head + SAC are MANDATORY** |

**We are in the "< 65%" band by a wide margin.** Architecture tasks #3 (bge-m3 dense+sparse+ColBERT RRF) and #4 (Summary-Augmented Chunking + parent-child) must land before further verifier tuning can move the ceiling.

## What this means for the 88% battery pass rate

The 88% number we hit in round-7 came from queries where:
- ✓ retrieval surfaced something relevant (even if not the gold passage)
- ✓ the model wrote cited sentences against those
- ✓ NLI confirmed the citations

The audit reveals that **for 47% of in-slice queries, the model is grounding its answer in passages that aren't the actual landmark authority on the topic**. The citation guarantee still holds (every cited sentence is supported by the cited passage), but the *legal authority* of the citation is weaker than it should be — we're citing the closest-thing-in-top-20 rather than the canonical precedent.

## Per-query results

| Query | Subject | Found? | Rank | Top-5 we got |
|---|---|---|---|---|
| Police didn't file FIR | criminal | ✓ | 1 | Sakiri Vasu (gold) at #1 |
| Anticipatory bail | criminal | ✓ | 4 | Gurbaksh Singh Sibbia (gold) at #4 |
| Punishment for theft | criminal | ✗ | — | Tofan Singh (drugs), BNS act header (not theft section), BNSS (procedural) |
| Confession to police admissible | criminal | ✗ | — | Tofan Singh, Maharashtra v Kamal Ahmed (POTA), Ayyub (different topic) |
| Cognizable vs non-cognizable | criminal | ✗ | — | Om Prakash, UoI v Ashok Kumar Sharma, Gangadhar — all procedural but not the definitional sections |
| Husband threatens / domestic violence | family | ✓ | 12 | Indra Sarma / V.D. Bhanot family at #12 |
| Divorce on cruelty | family | ✓ | 13 | Naveen Kohli / Samar Ghosh at #13 |
| Custody of child | family | ✗ | — | Mohan Kumar Rayana, Nithya Anand Raghavan (custody cases but NOT the named gold landmarks like Gautam Kundu) |
| Unpaid salary recovery | wages | ✓ | 6 | P.C. Aggarwala (Payment of Wages) at #6 |
| Fired without notice | wages | ✗ | — | Reetu Marbles, Batala Cooperative, Ramesh Kumar — Industrial Disputes Sec 25F not surfaced |
| RTI rejected, appeal | rti | ✗ | — | Anjali Bhardwaj cases (relevant) but Sec 19 RTI Act not in top-20 |
| Road accident compensation | motor | ✓ | 5 | Motor Vehicles act / Section 166 at #5 |
| Builder delay flat | consumer | ✓ | 2 | Experion Developers (gold) at #2 |
| Doctor wrong treatment | consumer | ✓ | 3 | Jacob Mathew (medical-negligence landmark) at #3 |
| Punishment for theft (dup) | criminal | ✗ | — | (same as above) |

## Patterns in the misses

1. **Statute-section retrieval is broken.** "Punishment for theft" should pull Section 379 / BNS theft section verbatim. Our act chunks aren't getting matched because the *query* doesn't share lexical overlap with the *section heading*. The query says "punishment for theft"; the act section title is "Theft" with surrounding clause text. This is exactly what BGE-M3's learned-sparse head (SPLADE-style) is built to handle.

2. **Definitional vs procedural confusion.** "Cognizable vs non-cognizable" needs the Section 2 definitions of CrPC/BNSS. We retrieved random procedural cases. Same root cause: query phrasing doesn't match where the definition lives in the act.

3. **Custody and family queries surfaced reasonable cases that AREN'T the named landmarks in my gold list.** Mohan Kumar Rayana, Nithya Anand Raghavan are real custody judgments. This is a **methodology caveat**: my gold list may be too narrow. If I expand to "any judgment whose holding addresses the query," recall would jump.

4. **Even when gold is found, ranks are often poor.** Recall@8 = 40% means MOST of the time the top-8 (what we feed the LLM) doesn't have the gold. The cross-encoder reranker is doing some heavy lifting here, but it can't surface what dense retrieval didn't deliver.

## Methodology caveats

- N = 15. Small but the signal is strong: 7 misses isn't statistical noise.
- Gold lists are conservative (specific landmark names). Permissive gold ("any judgment that addresses the query holding") would lift recall meaningfully — possibly to the 65-75% band — but still below the 85% "retrieval is fine" line.
- Audit was run AGAINST the current production endpoint (bge-m3 dense @ halfvec(1024) + Postgres BM25). No code change.

## Recommended next action

Run Task #3 (bge-m3 dense + sparse + ColBERT RRF) before further verifier tuning. Specifically, the **learned-sparse head** is built to fix "Section 154(3) Cr.P.C." exact-citation queries that pure dense retrieval bungles. The Summary-Augmented Chunking (Task #4) addresses the wrong-document retrieval pattern visible in the custody/labor misses.

After #3 + #4 land:
- Re-run this audit. Target: recall@20 ≥ 85%.
- Then re-run battery v3. Target: 88% → 95%+ honestly (no threshold changes).
