from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.predict import PredictResponse


class PredictService:
    def __init__(self) -> None:
        base = Path(__file__).resolve().parents[2]
        self.ranked_path = base / "scr_output" / "topjobs_ads" / "ranked_jobs.json"

    def predict(self, keyword: str, top_k: int) -> PredictResponse:
        records = []
        if self.ranked_path.exists():
            try:
                records = json.loads(self.ranked_path.read_text(encoding="utf-8"))
            except Exception:
                records = []
        if not isinstance(records, list):
            records = []

        if keyword.strip():
            key = keyword.strip().lower()
            filtered = [r for r in records if key in str(r.get("position", "")).lower()]
        else:
            filtered = records

        sorted_rows = sorted(filtered, key=lambda row: float(row.get("match_percent", 0)), reverse=True)[:top_k]

        recommended_roles = []
        for row in sorted_rows:
            url = row.get("url", "")
            recommended_roles.append(
                {
                    "position": str(row.get("position", "Untitled role")),
                    "employer": str(row.get("employer", "Unknown employer")),
                    "matchPercent": round(float(row.get("match_percent", 0)), 2),
                    "explanation": row.get("explanations", ["Ranked by weighted skill match."]),
                    "supportingAds": ([{"ref": row.get("ref", ""), "url": url}] if url else []),
                }
            )

        return PredictResponse(
            keyword=keyword.strip(),
            generatedAt=datetime.now(timezone.utc).isoformat(),
            recommendedRoles=recommended_roles,
        )
