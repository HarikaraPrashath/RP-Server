from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.engines.nlp.preprocess import normalize_text


@dataclass
class DedupResult:
    kept: list[dict[str, Any]]
    dropped: int


def _sig(job: dict[str, Any]) -> str:
    ref = str(job.get("ref", "")).strip().lower()
    url = str(job.get("url", "")).strip().lower()
    position = normalize_text(str(job.get("position", "")))
    employer = normalize_text(str(job.get("employer", "")))
    files = ",".join(sorted(str(f).lower() for f in (job.get("files") or [])))
    base = "|".join([ref, url, position, employer, files])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def deduplicate_metadata(rows: list[dict[str, Any]]) -> DedupResult:
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in rows:
        sig = _sig(row)
        if sig in seen:
            dropped += 1
            continue
        seen.add(sig)
        kept.append(row)
    return DedupResult(kept=kept, dropped=dropped)
