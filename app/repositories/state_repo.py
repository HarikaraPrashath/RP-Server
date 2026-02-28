from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.compat import QueryState


class StateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str) -> dict | None:
        stmt = select(QueryState).where(QueryState.key == key)
        row = self.db.scalar(stmt)
        if row is None:
            return None
        return row.value if isinstance(row.value, dict) else None

    def upsert(self, key: str, value: dict) -> None:
        stmt = select(QueryState).where(QueryState.key == key)
        row = self.db.scalar(stmt)
        if row is None:
            row = QueryState(key=key, value=value)
            self.db.add(row)
        else:
            row.value = value
        self.db.flush()
