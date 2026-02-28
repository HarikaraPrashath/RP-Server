from __future__ import annotations

from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.compat import CvFile


class CvRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        file_id: str,
        user_id: str | None,
        original_name: str,
        content_type: str,
        size: int,
        storage_path: Path,
        uploaded_at,
    ) -> CvFile:
        row = CvFile(
            id=file_id,
            user_id=user_id,
            original_name=original_name,
            content_type=content_type,
            size=size,
            storage_path=str(storage_path),
            uploaded_at=uploaded_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest(self, user_id: str | None = None) -> CvFile | None:
        stmt = select(CvFile)
        if user_id:
            stmt = stmt.where(CvFile.user_id == user_id)
        stmt = stmt.order_by(desc(CvFile.uploaded_at)).limit(1)
        return self.db.scalar(stmt)

    def get_by_id(self, file_id: str) -> CvFile | None:
        stmt = select(CvFile).where(CvFile.id == file_id)
        return self.db.scalar(stmt)
