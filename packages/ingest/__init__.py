"""Ingestion: per-source adapters + PDF/OCR normalize + PII redaction.

Pipeline (per PLAN §1, §10.2):
    adapter.fetch() -> raw_bytes
    normalize.pdf_to_text(raw_bytes) -> text
    normalize.redact.redact(text) -> (clean_text, redaction_report)
    -> handed off to chunking (Day 6-7)
"""
__version__ = "0.1.0"
