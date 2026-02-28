from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.db.models.compat import TrendSnapshot


class TrendRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_snapshot(self, *, ran_at: datetime, keyword: str, job_count: int, skill_counts: dict, role_counts: dict) -> TrendSnapshot:
        row = TrendSnapshot(
            ran_at=ran_at,
            keyword=keyword,
            job_count=job_count,
            skill_counts=skill_counts,
            role_counts=role_counts,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_history(self) -> list[TrendSnapshot]:
        stmt = select(TrendSnapshot).order_by(TrendSnapshot.ran_at.asc())
        return list(self.db.scalars(stmt).all())

    def replace_history(self, rows: list[dict]) -> None:
        self.db.execute(delete(TrendSnapshot))
        for row in rows:
            self.add_snapshot(
                ran_at=row["ran_at"],
                keyword=row.get("keyword", ""),
                job_count=int(row.get("job_count", 0)),
                skill_counts=row.get("skill_counts", {}),
                role_counts=row.get("role_counts", {}),
            )

    def prune_before(self, cutoff: datetime) -> None:
        # Delete rows older than cutoff.
        stmt = delete(TrendSnapshot).where(TrendSnapshot.ran_at < cutoff)
        self.db.execute(stmt)

    def latest(self) -> TrendSnapshot | None:
        stmt = select(TrendSnapshot).order_by(desc(TrendSnapshot.ran_at)).limit(1)
        return self.db.scalar(stmt)
