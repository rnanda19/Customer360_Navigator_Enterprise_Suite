"""
src/services/bp3_inference_service.py — Customer360 Navigator

BP3 (Complaint Escalation / Intervention Prediction) FastAPI inference service - Hardening Step 3.
Self-contained and independently deployable (run with `uvicorn services.bp3_inference_service:app`),
mirroring BP1's and BP2's own service files and the AMEX RiskIQ platform's established one-service-
file-per-problem pattern.

Loads the champion model bundle persisted by
notebooks/bp3_complaint_escalation_prediction/bp3_complaint_escalation_prediction_model_persistence.ipynb
(Hardening Step 2) at startup via src/services/service_common.py (shared with BP1's/BP2's services,
HYPER). Never fabricates a prediction: if that notebook has not yet been run for real, the service
still starts (so it can be health-checked and diagnosed) but serves 503 on /predict.

Request schema note: BP3's real feature columns include names with spaces and hyphens
("Sub-product", "Submitted via") that are not valid Python identifiers, so the request item model
is built dynamically from src/features/bp3_escalation_features.py's own FEATURE_COLS_CATEGORICAL +
COMPANY_COL constants (never hand-typed a second time - single source of truth, same constants the
persisted bundle's preprocessor was actually fit on), the same dynamic-Pydantic-model pattern
BP2's service already established.

Response schema note: BP3 differs from BP1's/BP2's multi-class services - its target is binary
(intervention_required, 0/1), so predict_bp3() returns a raw 0/1 predicted_label and a
probability_positive_class field rather than a ranked top-3 label list (top3_from_proba() would be
meaningless for 2 classes - it would just repeat rank-2/rank-3 as padding). This service's
BP3Prediction model reflects that real, different shape rather than forcing BP1's/BP2's ranked
response format onto a binary problem it does not fit.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, create_model

_THIS_FILE_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_THIS_FILE_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_FILE_SRC_DIR))

from features.bp3_escalation_features import (  # noqa: E402
    COMPANY_COL,
    FEATURE_COLS_CATEGORICAL,
)
from models.model_persistence import predict_bp3  # noqa: E402
from services.service_auth import require_api_key  # noqa: E402
from services.service_common import (  # noqa: E402
    HealthResponse,
    ModelBundleHandle,
    build_health_response,
    resolve_project_root,
)

BP_ID = "bp3"
MAX_BATCH_SIZE = 100
_REAL_COLS = list(FEATURE_COLS_CATEGORICAL) + [COMPANY_COL]

_handle: Optional[ModelBundleHandle] = None


def _default_joblib_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib"


def _default_metadata_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp3_complaint_escalation_prediction" / "bp3_model_metadata.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = ModelBundleHandle(BP_ID, _default_joblib_path(), _default_metadata_path())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP3 Complaint Escalation Prediction",
    description="Predicts whether a complaint requires intervention (monetary relief) from its "
    "real structured CFPB fields.",
    version="0.1.0",
    lifespan=lifespan,
)


def _safe_field_name(col: str) -> str:
    return col.replace(" ", "_").replace("-", "_")


_item_fields = {
    _safe_field_name(col): (
        str,
        Field(
            ...,
            alias=col,
            min_length=1,
            description=f"Real value for the '{col}' column.",
        ),
    )
    for col in _REAL_COLS
}
BP3PredictItem = create_model(  # noqa: N806 - conventional PascalCase for a dynamically built model
    "BP3PredictItem",
    __config__=ConfigDict(populate_by_name=True),
    **_item_fields,
)


class BP3PredictRequest(BaseModel):
    items: list[BP3PredictItem] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Complaint feature rows to classify (1-{MAX_BATCH_SIZE} per request). "
        f"Each item's real keys are: {_REAL_COLS}.",
    )


class BP3Prediction(BaseModel):
    predicted_label: int = Field(description="0 = no intervention required, 1 = intervention required.")
    probability_positive_class: float = Field(
        description="Predicted probability of intervention_required=1 (the real decision-threshold "
        "quantity BP3's Gate 5 uses, default threshold 0.5)."
    )
    confidence: float = Field(description="max(probability_positive_class, 1 - probability_positive_class).")


class BP3PredictResponse(BaseModel):
    champion_model: str
    decision_threshold: float = 0.5
    predictions: list[BP3Prediction]


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp3_complaint_escalation_prediction",
        "docs": "/docs",
        "health": "/health",
        "predict": "/predict",
        "required_fields": _REAL_COLS,
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    return build_health_response(_handle)


@app.post(
    "/predict",
    response_model=BP3PredictResponse,
    tags=["inference"],
    dependencies=[Depends(require_api_key)],
)
def predict(request: BP3PredictRequest):
    if _handle is None or not _handle.is_loaded:
        error = _handle.error if _handle is not None else "Model handle not initialized."
        raise HTTPException(status_code=503, detail=f"BP3 model is not loaded: {error}")

    rows = [item.model_dump(by_alias=True) for item in request.items]
    X_raw = pd.DataFrame(rows, columns=_REAL_COLS)

    result = predict_bp3(_handle.bundle, X_raw)
    predictions = [
        BP3Prediction(
            predicted_label=int(pred_label),
            probability_positive_class=round(float(proba_pos), 6),
            confidence=round(float(conf), 6),
        )
        for pred_label, proba_pos, conf in zip(
            result["predicted_label"], result["probability_positive_class"], result["confidence"]
        )
    ]

    return BP3PredictResponse(
        champion_model=_handle.bundle["champion_name"],
        predictions=predictions,
    )
