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
}

export interface DisclaimerEvent {
  text: string;
}

export interface ErrorEvent {
  message: string;
}
