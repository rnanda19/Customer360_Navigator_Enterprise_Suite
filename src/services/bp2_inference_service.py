"""
src/services/bp2_inference_service.py — Customer360 Navigator

BP2 (Customer Friction Classification) FastAPI inference service - Hardening Step 3. Self-
contained and independently deployable (run with `uvicorn services.bp2_inference_service:app`),
mirroring BP1's own service file and the AMEX RiskIQ platform's established one-service-file-per-
problem pattern.

Loads the champion model bundle persisted by
notebooks/bp2_customer_friction_classification/bp2_customer_friction_classification_model_persistence.ipynb
(Hardening Step 2) at startup via src/services/service_common.py (shared with BP1's service,
HYPER). Never fabricates a prediction: if that notebook has not yet been run for real, the service
still starts (so it can be health-checked and diagnosed) but serves 503 on /predict.

Request schema note: BP2's real feature columns include names with spaces and hyphens
("Sub-product", "Submitted via") that are not valid Python identifiers, so the request item model
is built dynamically from src/features/bp2_friction_features.py's own FEATURE_COLS_CATEGORICAL +
COMPANY_COL constants (never hand-typed a second time - single source of truth, same constants
the persisted bundle's preprocessor was actually fit on) using pydantic field aliases, the same
"dynamic Pydantic model for many real columns" pattern already established on the AMEX RiskIQ
platform's own severity-scoring service.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, create_model

_THIS_FILE_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_THIS_FILE_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_FILE_SRC_DIR))

from features.bp2_friction_features import (  # noqa: E402
    COMPANY_COL,
    FEATURE_COLS_CATEGORICAL,
)
from models.model_persistence import predict_bp2  # noqa: E402
from services.service_auth import require_api_key  # noqa: E402
from services.service_common import (  # noqa: E402
    HealthResponse,
    ModelBundleHandle,
    build_health_response,
    resolve_project_root,
    top3_from_proba,
)

BP_ID = "bp2"
MAX_BATCH_SIZE = 100
_REAL_COLS = list(FEATURE_COLS_CATEGORICAL) + [COMPANY_COL]

_handle: Optional[ModelBundleHandle] = None


def _default_joblib_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp2_customer_friction_classification" / "bp2_champion_bundle.joblib"


def _default_metadata_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp2_customer_friction_classification" / "bp2_model_metadata.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = ModelBundleHandle(BP_ID, _default_joblib_path(), _default_metadata_path())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP2 Customer Friction Classification",
    description="Predicts a complaint's friction-severity class from its real structured CFPB fields.",
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
BP2PredictItem = create_model(  # noqa: N806 - conventional PascalCase for a dynamically built model
    "BP2PredictItem",
    __config__=ConfigDict(populate_by_name=True),
    **_item_fields,
)


class BP2PredictRequest(BaseModel):
    items: list[BP2PredictItem] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Complaint feature rows to classify (1-{MAX_BATCH_SIZE} per request). "
        f"Each item's real keys are: {_REAL_COLS}.",
    )


class BP2Prediction(BaseModel):
    predicted_label: str
    confidence: float
    rank2_label: str
    rank2_confidence: float
    rank3_label: str
    rank3_confidence: float


class BP2PredictResponse(BaseModel):
    champion_model: str
    n_classes: int
    predictions: list[BP2Prediction]


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp2_customer_friction_classification",
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
    response_model=BP2PredictResponse,
    tags=["inference"],
    dependencies=[Depends(require_api_key)],
)
def predict(request: BP2PredictRequest):
    if _handle is None or not _handle.is_loaded:
        error = _handle.error if _handle is not None else "Model handle not initialized."
        raise HTTPException(status_code=503, detail=f"BP2 model is not loaded: {error}")

    rows = [item.model_dump(by_alias=True) for item in request.items]
    X_raw = pd.DataFrame(rows, columns=_REAL_COLS)

    result = predict_bp2(_handle.bundle, X_raw)
    class_names = result["class_names"]
    probabilities = np.asarray(result["probabilities"])

    predictions = []
    for proba_row in probabilities:
        label1, conf1, label2, conf2, label3, conf3 = top3_from_proba(proba_row, class_names)
        predictions.append(
            BP2Prediction(
                predicted_label=label1,
                confidence=round(conf1, 6),
                rank2_label=label2,
                rank2_confidence=round(conf2, 6),
                rank3_label=label3,
                rank3_confidence=round(conf3, 6),
            )
        )

    return BP2PredictResponse(
        champion_model=_handle.bundle["champion_name"],
        n_classes=len(class_names),
        predictions=predictions,
    )
