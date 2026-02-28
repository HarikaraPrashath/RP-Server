from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    keyword: str = ""
    topK: int = Field(default=5, ge=1, le=20)


class RecommendedRole(BaseModel):
    position: str
    employer: str
    matchPercent: float
    explanation: list[str]
    supportingAds: list[dict]


class PredictResponse(BaseModel):
    keyword: str
    generatedAt: str
    recommendedRoles: list[RecommendedRole]
