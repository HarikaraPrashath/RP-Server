from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.token import PasswordResetToken, RefreshToken


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def store_refresh_token(self, user_id: str, token_hash: str, jti: str, expires_at: datetime) -> RefreshToken:
        row = RefreshToken(user_id=user_id, token_hash=token_hash, jti=jti, expires_at=expires_at)
        self.db.add(row)
        self.db.flush()
        return row

    def get_valid_refresh_token(self, user_id: str, jti: str, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.jti == jti,
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        return self.db.scalar(stmt)

    def revoke_refresh_token(self, user_id: str, jti: str, token_hash: str) -> bool:
        row = self.get_valid_refresh_token(user_id=user_id, jti=jti, token_hash=token_hash)
        if row is None:
            return False
        row.revoked_at = utcnow()
        self.db.flush()
        return True

    def store_reset_token(self, user_id: str, token_hash: str, expires_at: datetime) -> PasswordResetToken:
        row = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(row)
        self.db.flush()
        return row

    def get_valid_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utcnow(),
        )
        return self.db.scalar(stmt)

    def mark_reset_token_used(self, row: PasswordResetToken) -> None:
        row.used_at = utcnow()
        self.db.flush()
