from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.profile import Profile


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: str) -> Profile | None:
        stmt = select(Profile).where(Profile.user_id == user_id)
        return self.db.scalar(stmt)

    def upsert(self, user_id: str, payload: dict) -> Profile:
        profile = self.get_by_user_id(user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            self.db.add(profile)
        profile.basics = payload.get("basics", {})
        profile.about = payload.get("about", "")
        profile.experiences = payload.get("experiences", [])
        profile.education_items = payload.get("educationItems", [])
        profile.skills = payload.get("skills", [])
        profile.projects = payload.get("projects", [])
        profile.certifications = payload.get("certifications", [])
        profile.recommendations = payload.get("recommendations", [])
        self.db.flush()
        return profile
