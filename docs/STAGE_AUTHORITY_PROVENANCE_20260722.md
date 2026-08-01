# Authority Provenance and Safe-Handoff Closure (2026-07-22)

## Purpose

This stage hardens two product boundaries that must remain reliable before
answer quality can be evaluated fairly: public evidence identity and safe
failure when required authority cannot be verified.

## Architecture Decisions

1. `RetrievedChunk.anchor` is immutable corpus provenance. A focused retrieval
   view may supply `display_anchor`, but every public passage and `sources` SSE
   record must also include `canonical_anchor`, stable `document_id`, and
   `chunk_id`. The normal model-backed stream and the reviewed-template stream
   use the same public provenance fields.
2. A source-gap handoff accepts only a typed payload with a boolean `has_gap`
   marker and at least one complete diagnostic: non-empty `gap_kinds` or a
   non-empty `missing_required_sources` list. A complete concrete missing-source
   record remains valid when an older producer omitted `gap_kinds`.
3. Schema validation is recursive for public provenance: every
   `required_anchor_patterns` entry must be a non-empty string. Invalid nested
   values are not silently discarded; they produce the observable
   `invalid_source_gap_payload` safe handoff.
4. Plain-language relative-adoption routing recognizes phrases such as
   "want to adopt my sister's child" while rejecting clearly non-personal
   contexts such as a child-friendly leave policy, a child-protection policy,
   or adopting a pet for a child.

## Evidence

- Exact official Juvenile Justice Act adoption sections were promoted locally
  from the existing official PDF without adding corpus data to Git.
- Live replay verified `jj-2015/sec-58-official` is emitted with its canonical
  anchor, display anchor, document key, and verified chunk ID.
- Independent reviews found and the implementation fixed: canonical JJ anchor
  mutation, incomplete source events, broad present-tense adoption routing, and
  malformed nested anchor diagnostics.
- Targeted API and router tests passed after each follow-up; the final complete
  API suite passed `2354`, with one explicitly skipped opt-in live-Postgres
  provenance test.

## Release Boundary

This work makes source identity and safe handoffs more trustworthy. It does not
prove broad legal-answer quality or production readiness. The next required
evidence is a fresh, exact-prompt-excluded 500-row synthetic human-like live
evaluation, followed by independent labeling or real-user telemetry before any
launch claim.
