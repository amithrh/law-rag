// SSE event payloads emitted by the FastAPI /answer endpoint.
// Keep these in sync with apps/api/main.py.

export type SentenceStatus =
  | "ok"
  | "weak_support"
  | "unsupported"
  | "unknown_citation"
  | "meta";

export interface CoverageEvent {
  sources_searched: string[];
  subjects_in_results: string[];
  passages_used: number;
}

export interface PassageEvent {
  index: number;
  anchor: string;
  title: string;
  as_at: string | null;
  court: string | null;
  citation: string | null;
}

export interface SentenceEvent {
  text: string;
  status: SentenceStatus;
  citations: number[];
  entailment_score: number | null;
  reason: string | null;
  auto_cited?: boolean;
}

export interface StopEvent {
  reason: string;
  message: string;
  unsupported_count: number;
  emitted_count: number;
}

export interface RefusedEvent {
  message: string;
  disclaimer: string;
  // Server-tagged reason so the UI can show different copy for each
  // refusal class. "rerank_unavailable" = service degraded (retry).
  // "low_coverage" / "low_coverage_dense_fallback" = corpus gap (rephrase).
  // Absent for the legacy empty-retrieval refusal.
  reason?: "rerank_unavailable" | "low_coverage" | "low_coverage_dense_fallback";
  top_rerank_score?: number;
  top_combined_score?: number;
}

// Server-authored authoritative sources event, emitted at end of stream.
// Per round-3 review: the LLM-authored Sources prose is suppressed; this
// event carries the canonical metadata from the retrieval result.
export type SourcesEvent = PassageEvent[];

// Lightweight marker emitted when the server suppresses an uncited or
// weak-auto-cited sentence. UI renders as "…" so users can see that a
// claim was dropped — the suppress path was previously invisible.
export interface SuppressedEvent {
  // Currently empty; reserved for future fields (e.g. count, reason).
}

// Task #10: answer-vs-query relevance check. Emitted after `sources` and
// before `disclaimer` on the normal end-of-stream path. NOT emitted on
// refused / stopped / empty-body paths. ADDITIVE signal — the UI may
// render a notice for "partial" / "off_topic" verdicts, but the answer
// itself is unaffected (citations still ground the prose).
export type RelevanceVerdict = "ok" | "partial" | "off_topic";

export interface RelevanceEvent {
  // bge-m3 cosine between the original user query and the assembled
  // user-visible answer body (OK + WEAK_SUPPORT sentence texts).
  score: number;
  verdict: RelevanceVerdict;
  // Calibrated threshold used by the server to classify this score.
  // Sent so the UI / debug tooling can render the distance to the
  // boundary without hardcoding the value.
  threshold: number;
  // PARTIAL band width — verdicts inside [threshold-band/2,
  // threshold+band/2] are "partial".
  band: number;
}

export interface DisclaimerEvent {
  text: string;
}

export interface ErrorEvent {
  message: string;
}
