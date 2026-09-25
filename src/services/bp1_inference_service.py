"""
src/services/bp1_inference_service.py — Customer360 Navigator

BP1 (Customer Intent Classification) FastAPI inference service - Hardening Step 3. Self-contained
and independently deployable (run with `uvicorn services.bp1_inference_service:app`), mirroring
the AMEX RiskIQ platform's own established one-service-file-per-problem pattern so Step 5's Docker
packaging can give this its own self-contained container exactly the way AMEX's Problems 3/4/5
each did.

Loads the champion model bundle persisted by
notebooks/bp1_customer_intent_classification/bp1_customer_intent_classification_model_persistence.ipynb
(Hardening Step 2) at startup via src/services/service_common.py (shared with BP2's service,
HYPER). Never fabricates a prediction: if that notebook has not yet been run for real, the service
still starts (so it can be health-checked and diagnosed) but serves 503 on /predict with a message
naming exactly what to run.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

_THIS_FILE_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_THIS_FILE_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_FILE_SRC_DIR))

from models.model_persistence import predict_bp1  # noqa: E402
from services.service_common import (  # noqa: E402
    HealthResponse,
    ModelBundleHandle,
    build_health_response,
    resolve_project_root,
    top3_from_proba,
)

BP_ID = "bp1"
MAX_BATCH_SIZE = 100

_handle: Optional[ModelBundleHandle] = None


def _default_joblib_path() -> Path:
    """Never hardcodes a real local machine path (the exact privacy/portability bug found and
    fixed on the AMEX RiskIQ platform's own equivalent service) - always resolved relative to the
    project root, itself resolved without any hardcoded absolute path."""
    project_root = resolve_project_root()
    return project_root / "models" / "bp1_customer_intent_classification" / "bp1_champion_pipeline.joblib"


def _default_metadata_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp1_customer_intent_classification" / "bp1_model_metadata.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = ModelBundleHandle(BP_ID, _default_joblib_path(), _default_metadata_path())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP1 Customer Intent Classification",
    description="Predicts a customer's BANKING77 intent class from raw complaint/message text.",
    version="0.1.0",
    lifespan=lifespan,
)


class BP1PredictRequest(BaseModel):
    texts: list[str] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Raw customer message texts to classify (1-{MAX_BATCH_SIZE} per request).",
    )

    @field_validator("texts")
    @classmethod
    def _no_blank_texts(cls, v: list[str]) -> list[str]:
        for t in v:
            if not t or not t.strip():
                raise ValueError("texts must not contain empty or whitespace-only strings.")
        return v


class BP1Prediction(BaseModel):
    text: str
    predicted_label: str
    confidence: float
    rank2_label: str
    rank2_confidence: float
    rank3_label: str
    rank3_confidence: float


class BP1PredictResponse(BaseModel):
    champion_model: str
    n_classes: int
    predictions: list[BP1Prediction]


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp1_customer_intent_classification",
        "docs": "/docs",
        "health": "/health",
        "predict": "/predict",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    return build_health_response(_handle)


@app.post("/predict", response_model=BP1PredictResponse, tags=["inference"])
def predict(request: BP1PredictRequest):
    if _handle is None or not _handle.is_loaded:
        error = _handle.error if _handle is not None else "Model handle not initialized."
        raise HTTPException(status_code=503, detail=f"BP1 model is not loaded: {error}")

    result = predict_bp1(_handle.bundle, request.texts)
    class_names = result["class_names"]
    probabilities = np.asarray(result["probabilities"])

    predictions = []
    for text, proba_row in zip(request.texts, probabilities):
        label1, conf1, label2, conf2, label3, conf3 = top3_from_proba(proba_row, class_names)
        predictions.append(
            BP1Prediction(
                text=text,
                predicted_label=label1,
                confidence=round(conf1, 6),
                rank2_label=label2,
                rank2_confidence=round(conf2, 6),
                rank3_label=label3,
                rank3_confidence=round(conf3, 6),
            )
        )

    return BP1PredictResponse(
        champion_model=_handle.bundle["champion_name"],
        n_classes=len(class_names),
        predictions=predictions,
    )
