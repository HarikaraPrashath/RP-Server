from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import ProfileRepository


DEFAULT_PROFILE = {
    "basics": {
        "firstName": "",
        "lastName": "",
        "additionalName": "",
        "headline": "",
        "position": "",
        "industry": "",
        "school": "",
        "country": "",
        "city": "",
        "contactEmail": "",
        "showCurrentCompany": True,
        "showSchool": True,
    },
    "about": "",
    "experiences": [],
    "educationItems": [],
    "skills": [],
    "projects": [],
    "certifications": [],
    "recommendations": [],
}


class ProfileService:
    def __init__(self, db: Session):
        self.repo = ProfileRepository(db)

    def get_profile(self, user_id: str, email: str) -> dict:
        profile = self.repo.get_by_user_id(user_id)
        if profile is None:
            payload = {**DEFAULT_PROFILE}
            payload["basics"] = {**DEFAULT_PROFILE["basics"], "contactEmail": email}
            return payload
        return {
            "basics": profile.basics,
            "about": profile.about,
            "experiences": profile.experiences,
            "educationItems": profile.education_items,
            "skills": profile.skills,
            "projects": profile.projects,
            "certifications": profile.certifications,
            "recommendations": profile.recommendations,
        }

    def update_profile(self, user_id: str, payload: dict) -> dict:
        profile = self.repo.upsert(user_id=user_id, payload=payload)
        return {
            "basics": profile.basics,
            "about": profile.about,
            "experiences": profile.experiences,
            "educationItems": profile.education_items,
            "skills": profile.skills,
            "projects": profile.projects,
            "certifications": profile.certifications,
            "recommendations": profile.recommendations,
        }
