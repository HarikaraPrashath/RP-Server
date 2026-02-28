from __future__ import annotations

from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_jwt,
    hash_password,
    hash_token,
    new_salt,
    verify_password,
)
from app.db.models.user import UserRole
from app.repositories import TokenRepository, UserRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.tokens = TokenRepository(db)

    def signup(self, email: str, password: str, confirm_password: str, role: str = "student") -> dict:
        if password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")
        if self.users.get_by_email(email):
            raise HTTPException(status_code=409, detail="Account already exists.")
        try:
            role_enum = UserRole(role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid role.") from exc

        salt = new_salt()
        user = self.users.create(
            email=email,
            password_hash=hash_password(password, salt),
            password_salt=salt.hex(),
            role=role_enum,
        )
        access_token, _, access_exp = create_access_token(subject=user.id, role=user.role.value)
        refresh_token, refresh_jti, refresh_exp = create_refresh_token(subject=user.id, role=user.role.value)
        self.tokens.store_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            jti=refresh_jti,
            expires_at=refresh_exp,
        )
        self.db.commit()
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "tokenType": "bearer",
            "expiresIn": int((access_exp - _utcnow()).total_seconds()),
            "user": {"id": user.id, "email": user.email, "role": user.role.value},
        }

    def login(self, email: str, password: str) -> dict:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_salt, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        access_token, _, access_exp = create_access_token(subject=user.id, role=user.role.value)
        refresh_token, refresh_jti, refresh_exp = create_refresh_token(subject=user.id, role=user.role.value)
        self.tokens.store_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            jti=refresh_jti,
            expires_at=refresh_exp,
        )
        self.db.commit()
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "tokenType": "bearer",
            "expiresIn": int((access_exp - _utcnow()).total_seconds()),
            "user": {"id": user.id, "email": user.email, "role": user.role.value},
        }

    def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_jwt(refresh_token)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid refresh token.") from exc

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")

        user_id = str(payload.get("sub", ""))
        role = str(payload.get("role", "student"))
        jti = str(payload.get("jti", ""))
        if not user_id or not jti:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload.")

        valid = self.tokens.get_valid_refresh_token(user_id=user_id, jti=jti, token_hash=hash_token(refresh_token))
        if valid is None:
            raise HTTPException(status_code=401, detail="Refresh token revoked or expired.")

        # Rotate token
        self.tokens.revoke_refresh_token(user_id=user_id, jti=jti, token_hash=hash_token(refresh_token))
        access_token, _, access_exp = create_access_token(subject=user_id, role=role)
        next_refresh, next_jti, next_exp = create_refresh_token(subject=user_id, role=role)
        self.tokens.store_refresh_token(user_id=user_id, token_hash=hash_token(next_refresh), jti=next_jti, expires_at=next_exp)
        self.db.commit()
        return {
            "accessToken": access_token,
            "refreshToken": next_refresh,
            "tokenType": "bearer",
            "expiresIn": int((access_exp - _utcnow()).total_seconds()),
            "user": {"id": user_id, "role": role},
        }

    def logout(self, user_id: str, refresh_token: str) -> dict:
        try:
            payload = decode_jwt(refresh_token)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid refresh token.") from exc
        jti = str(payload.get("jti", ""))
        revoked = self.tokens.revoke_refresh_token(user_id=user_id, jti=jti, token_hash=hash_token(refresh_token))
        self.db.commit()
        return {"ok": bool(revoked)}

    def forgot_password(self, email: str) -> dict:
        user = self.users.get_by_email(email)
        if user is None:
            return {"ok": True, "message": "If your account exists, a reset link has been sent."}
        plain, token_hash, expires = create_password_reset_token()
        self.tokens.store_reset_token(user_id=user.id, token_hash=token_hash, expires_at=expires)
        self.db.commit()
        response = {"ok": True, "message": "If your account exists, a reset link has been sent."}
        if settings.debug_password_reset_tokens:
            response["resetToken"] = plain
        return response

    def reset_password(self, token: str, new_password: str, confirm_password: str) -> dict:
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")
        token_row = self.tokens.get_valid_reset_token(hash_token(token))
        if token_row is None:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
        user = self.users.get_by_id(token_row.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        salt = new_salt()
        user.password_salt = salt.hex()
        user.password_hash = hash_password(new_password, salt)
        self.tokens.mark_reset_token_used(token_row)
        self.db.commit()
        return {"ok": True, "message": "Password has been reset successfully."}
