"""Privacy-safe identifiers for operational logs.

User questions can contain health, financial, family, or incident details.
Operational logs may use a stable short fingerprint for correlation, but must
never store the raw question or a truncated copy of it.
"""

from __future__ import annotations

import hashlib
import re


def query_fingerprint(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query).strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]
