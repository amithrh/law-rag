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

export interface DisclaimerEvent {
  text: string;
}

export interface ErrorEvent {
  message: string;
}
