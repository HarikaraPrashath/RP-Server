from __future__ import annotations

from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.rbac import ForbiddenRoleError
from app.core.security import decode_jwt
from app.db.session import SessionLocal
from app.repositories import UserRepository


bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token.")
    token = credentials.credentials
    try:
        payload = decode_jwt(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
    user_id = str(payload.get("sub", ""))
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    repo = UserRepository(db)
    user = repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user.")
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = decode_jwt(token)
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    user_id = str(payload.get("sub", ""))
    if not user_id:
        return None

    repo = UserRepository(db)
    user = repo.get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user


def require_roles(*roles: str):
    def _dependency(user=Depends(get_current_user)):
        if user.role.value not in roles:
            raise ForbiddenRoleError()
        return user

    return _dependency


def get_request_id(request: Request) -> str:
    return str(request.state.request_id)
