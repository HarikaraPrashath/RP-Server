from fastapi import APIRouter

from app.api.v1.routers import auth, compat, health, predict, profile

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, tags=["profile"])
api_router.include_router(predict.router, tags=["predict"])
api_router.include_router(compat.router, tags=["compat"])
