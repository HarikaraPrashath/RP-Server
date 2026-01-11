from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import joblib

app = FastAPI(title="Career Prediction API")

# -------------------------
# ADD CORS MIDDLEWARE (FIXES 405 OPTIONS ERROR)
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # allow all origins (OK for development)
    allow_credentials=True,
    allow_methods=["*"],          # allow POST, GET, OPTIONS
    allow_headers=["*"],
)

# -------------------------
# Load model + label encoder
# -------------------------
MODEL_PATH = "models/career_prediction_model.joblib"
ENC_PATH   = "models/career_label_encoder.joblib"

model = joblib.load(MODEL_PATH)
label_enc = joblib.load(ENC_PATH)

# -------------------------
# Input schema
# -------------------------
class StudentInput(BaseModel):
    Soft_Skills: str
    Key_Skils: str
    Current_semester: str
    Learning_Style: str
    GPA: float
    English_score: float
    Ocean_Openness: float
    Ocean_Conscientiousness: float
    Ocean_Extraversion: float
    Ocean_Agreeableness: float
    Ocean_Neuroticism: float
    Riasec_Realistic: float
    Riasec_Investigative: float
    Riasec_Artistic: float
    Riasec_Social: float
    Riasec_Enterprising: float
    Riasec_Conventional: float

# -------------------------
# Health check
# -------------------------
@app.get("/")
def root():
    return {"status": "Career Prediction API running"}

# -------------------------
# Predict endpoint (TOP-3)
# -------------------------
@app.post("/predict")
def predict(inp: StudentInput):
    df = pd.DataFrame([inp.dict()])

    probs = model.predict_proba(df)[0]
    top3_idx = np.argsort(probs)[-3:][::-1]
    top3_labels = label_enc.inverse_transform(top3_idx).tolist()

    return {
        "top_1_prediction": top3_labels[0],
        "top_3_predictions": top3_labels
    }
