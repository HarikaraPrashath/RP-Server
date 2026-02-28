from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_optional_current_user
from app.services.compat_service import CompatibilityService, load_profile_payload

router = APIRouter()
service = CompatibilityService()


@router.post("/parse")
async def parse_cv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_optional_current_user),
):
    return await service.parse_cv(file, db=db, user_id=(user.id if user else None))


@router.get("/cv")
def get_latest_cv(db: Session = Depends(get_db), user=Depends(get_optional_current_user)):
    return service.get_latest_cv(db=db, user_id=(user.id if user else None))


@router.get("/cv/file")
def get_cv_file(id: str, db: Session = Depends(get_db)):
    return service.get_cv_file_response(id, db=db)


@router.get("/jobs")
def get_jobs():
    return service.get_jobs()


@router.get("/jobs/file")
def get_job_file(name: str):
    return service.get_job_file_response(name)


@router.post("/jobs/refresh")
def refresh_jobs(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_optional_current_user),
):
    profile_payload = load_profile_payload(db, user) if user is not None else None
    return service.refresh_jobs(payload or {}, profile_payload, db=db)


@router.get("/jobs/refresh/status")
def refresh_jobs_status(jobId: str):
    return service.refresh_status(jobId)


@router.get("/ranked")
def get_ranked():
    return service.get_ranked()


@router.get("/ranked/summary")
def get_ranked_summary():
    return service.get_ranked_summary()


@router.get("/trends/history")
def get_trend_history(db: Session = Depends(get_db)):
    return service.get_trend_history(db=db)


@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    return service.get_trends(db=db)


@router.post("/trends/seed")
def seed_trends(payload: dict[str, Any] | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return service.seed_trends(payload or {}, db=db)


@router.post("/analyse")
async def analyse(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    profile_payload = load_profile_payload(db, user)
    return await service.analyse(payload or {}, profile_payload)
