from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.predict import PredictRequest
from app.services import PredictService

router = APIRouter()


@router.post("/predict")
def predict(payload: PredictRequest, user=Depends(get_current_user)):
    service = PredictService()
    return service.predict(payload.keyword, payload.topK)
