from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from app.services import AuthService

router = APIRouter()


@router.post("/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.signup(payload.email, payload.password, payload.confirmPassword, payload.role)


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.login(payload.email, payload.password)


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.refresh(payload.refreshToken)


@router.post("/logout")
def logout(payload: LogoutRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.logout(user.id, payload.refreshToken)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.forgot_password(payload.email)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.reset_password(payload.token, payload.newPassword, payload.confirmPassword)
