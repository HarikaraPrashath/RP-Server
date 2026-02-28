from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.profile import ProfilePayload
from app.services import ProfileService

router = APIRouter()


@router.get("/profile")
def get_profile(user=Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    return service.get_profile(user.id, user.email)


@router.put("/profile")
def update_profile(payload: ProfilePayload, user=Depends(get_current_user), db: Session = Depends(get_db)):
    service = ProfileService(db)
    updated = service.update_profile(user.id, payload.model_dump())
    db.commit()
    return updated
