from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex()


def new_salt() -> bytes:
    return secrets.token_bytes(16)


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hash_password(password, salt) == expected_hash


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_jwt(subject: str, role: str, token_type: str, expires_delta: timedelta, jti: str | None = None) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": jti or uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_access_token(subject: str, role: str) -> tuple[str, str, datetime]:
    expires = utcnow() + timedelta(minutes=settings.access_token_ttl_minutes)
    jti = uuid.uuid4().hex
    token = create_jwt(subject, role, "access", timedelta(minutes=settings.access_token_ttl_minutes), jti=jti)
    return token, jti, expires


def create_refresh_token(subject: str, role: str) -> tuple[str, str, datetime]:
    expires = utcnow() + timedelta(days=settings.refresh_token_ttl_days)
    jti = uuid.uuid4().hex
    token = create_jwt(subject, role, "refresh", timedelta(days=settings.refresh_token_ttl_days), jti=jti)
    return token, jti, expires


def create_password_reset_token() -> tuple[str, str, datetime]:
    plain = secrets.token_urlsafe(32)
    token_hash = hash_token(plain)
    expires = utcnow() + timedelta(minutes=settings.reset_token_ttl_minutes)
    return plain, token_hash, expires
