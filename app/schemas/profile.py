from __future__ import annotations

from pydantic import BaseModel, Field


class ProfilePayload(BaseModel):
    basics: dict = Field(default_factory=dict)
    about: str = ""
    experiences: list = Field(default_factory=list)
    educationItems: list = Field(default_factory=list)
    skills: list = Field(default_factory=list)
    projects: list = Field(default_factory=list)
    certifications: list = Field(default_factory=list)
    recommendations: list = Field(default_factory=list)


class ProfileResponse(ProfilePayload):
    pass
