"""
src/models/model_persistence.py — Customer360 Navigator

Generic joblib-based model persistence for this project's BP champion models. Hardening Step 2
(AMEX-RiskIQ-grade productization pass), companion to src/models/bp1_intent_classifier.py and
src/features/bp2_friction_features.py (which build/fit the objects this module saves and
reloads) - written so BOTH the BP1/BP2 model-persistence notebooks AND the future FastAPI
inference services (hardening Step 3) share one real, unit-tested save/load/predict
implementation instead of each reimplementing joblib.dump/load boilerplate independently
(HYPER - shared component built once, imported everywhere).

Design note on bundle shape: BP1's champion is a single self-contained sklearn Pipeline (TF-IDF
vectorizer + classifier, both steps inside one Pipeline object - see
src/models/bp1_intent_classifier.py's make_pipeline()). BP2's champion is NOT a single sklearn
Pipeline: its preprocessing (one-hot encoding of 7 low-cardinality columns + a plain-Python
company-frequency lookup, hstacked into one sparse matrix - see
src/features/bp2_friction_features.py's build_shared_preprocessing()) lives outside sklearn's
Pipeline abstraction by construction, because frequency-encoding a high-cardinality column is not
expressible as a stateless sklearn transformer step without writing a custom one - and Gates 3/4/5
(already real-run confirmed for both BPs) never did, so this module does not retroactively invent
one either. Rather than force BP2 into a single-Pipeline shape it was never actually fit as, this
module saves a plain, explicitly-keyed dict bundle for BOTH BPs - honest about what is actually
inside, and structurally identical to what Gates 3/4/5 already hold as separate in-memory objects
at refit time. BP3's champion (xgboost, real Gate 3 selection) is structurally the same
one-hot + company-frequency dict-bundle shape as BP2's - see src/features/bp3_escalation_features.py's
build_shared_preprocessing(), which is the same hstacked-sparse-matrix pattern BP2 uses. BP3 differs
from BP2 in one real, load-bearing way: its target (intervention_required) is already a binary
0/1 int column in the real Gate 3 notebook (cast via Polars .cast(pl.Int8), never passed through a
LabelEncoder anywhere in the real pipeline) - so BP3's bundle and predict_bp3() below have no
label_encoder key at all, unlike BP1's and BP2's multi-class bundles. Inventing one for BP3 would
be fabricating a component the real pipeline never fit. REQUIRED_KEYS below is the enforced
contract for each bp_id's bundle shape, checked on both save and load so a malformed or partial
bundle fails loudly and immediately rather than failing confusingly at inference time.

This module performs no execution of any BP's real data pipeline and is never run by Claude on
real project data - only imported and called by the user's own notebook runs (save side) and by
the FastAPI services built in Step 3 (load side).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy import sparse as sp

# ---------------------------------------------------------------------------
# Bundle contract - enforced on both save and load, so a malformed bundle fails loudly and
# immediately rather than confusingly at inference time.
# ---------------------------------------------------------------------------
REQUIRED_KEYS: dict[str, frozenset[str]] = {
    "bp1": frozenset(
        {
            "bp_id",
            "champion_name",
            "pipeline",
            "label_encoder",
            "class_names",
            "metadata",
        }
    ),
    "bp2": frozenset(
        {
            "bp_id",
            "champion_name",
            "preprocessor",
            "company_freq_map",
            "feature_cols_categorical",
            "company_col",
            "classifier",
            "label_encoder",
            "class_names",
            "needs_dense",
            "metadata",
        }
    ),
    "bp3": frozenset(
        {
            "bp_id",
            "champion_name",
            "preprocessor",
            "company_freq_map",
            "feature_cols_categorical",
            "company_col",
            "classifier",
            "class_names",
            "needs_dense",
            "metadata",
        }
    ),
}


def _validate_bundle(bundle: dict[str, Any]) -> str:
    bp_id = bundle.get("bp_id")
    if bp_id not in REQUIRED_KEYS:
        raise ValueError(
            f"Unknown or missing bp_id {bp_id!r} in model bundle - expected one of "
            f"{sorted(REQUIRED_KEYS)}."
        )
    missing = REQUIRED_KEYS[bp_id] - set(bundle.keys())
    if missing:
        raise ValueError(f"Model bundle for bp_id={bp_id!r} is missing required keys: {sorted(missing)}.")
    return bp_id


def save_model_bundle(bundle: dict[str, Any], path: Path) -> dict[str, Any]:
    """Validate `bundle` against REQUIRED_KEYS for its declared bp_id, joblib.dump it to `path`
    (creating parent directories if needed), and return real, freshly-computed file stats
    (size_bytes, sha256) for the caller to record in its own metadata JSON - never invented,
    always read back from the file actually written."""
    _validate_bundle(bundle)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path, compress=3)
    file_bytes = path.read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(file_bytes),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
    }


def load_model_bundle(path: Path) -> dict[str, Any]:
    """Load and validate a model bundle previously written by save_model_bundle(). Raises
    FileNotFoundError if the path does not exist, and ValueError if the loaded object is not a
    dict matching REQUIRED_KEYS for its own declared bp_id - never returns a partially-usable
    bundle silently."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found at {path}")
    bundle = joblib.load(path)
    if not isinstance(bundle, dict):
        raise ValueError(f"Loaded object at {path} is a {type(bundle).__name__}, not a dict bundle.")
    _validate_bundle(bundle)
    return bundle


def predict_bp1(bundle: dict[str, Any], texts) -> dict[str, Any]:
    """Run BP1's persisted TF-IDF + classifier pipeline end to end: raw text in, predicted intent
    label + confidence + full class-probability vector out. `texts` is any list-like of raw
    strings (the same FEATURE_COL the pipeline's TfidfVectorizer step was fit on - no separate
    vectorization step needed by the caller, it is the pipeline's own first step)."""
    if bundle.get("bp_id") != "bp1":
        raise ValueError(
            f"predict_bp1() called on a bundle with bp_id={bundle.get('bp_id')!r}, expected 'bp1'."
        )
    pipeline = bundle["pipeline"]
    label_encoder = bundle["label_encoder"]
    proba = np.asarray(pipeline.predict_proba(texts))
    pred_idx = np.argmax(proba, axis=1)
    return {
        "predicted_label": label_encoder.inverse_transform(pred_idx).tolist(),
        "confidence": proba[np.arange(len(pred_idx)), pred_idx].tolist(),
        "class_names": list(label_encoder.classes_),
        "probabilities": proba.tolist(),
    }


def predict_bp2(bundle: dict[str, Any], X_raw: pd.DataFrame) -> dict[str, Any]:
    """Run BP2's persisted one-hot + company-frequency + classifier bundle end to end: a raw
    feature DataFrame (columns = bundle['feature_cols_categorical'] + [bundle['company_col']]) in,
    predicted severity label + confidence + full class-probability vector out. An unseen company
    at inference time gets frequency 0 - never fabricated, the exact same fallback rule Gates
    3/4/5 already use for a test-set company absent from the train-fit frequency map (never
    inference/test-set-derived)."""
    if bundle.get("bp_id") != "bp2":
        raise ValueError(
            f"predict_bp2() called on a bundle with bp_id={bundle.get('bp_id')!r}, expected 'bp2'."
        )
    preprocessor = bundle["preprocessor"]
    company_freq_map = bundle["company_freq_map"]
    company_col = bundle["company_col"]
    classifier = bundle["classifier"]
    label_encoder = bundle["label_encoder"]

    X_ohe = preprocessor.transform(X_raw)
    freq = X_raw[company_col].map(company_freq_map).fillna(0).to_numpy(dtype=np.float32).reshape(-1, 1)
    X_shared = sp.hstack([X_ohe, sp.csr_matrix(freq)], format="csr")
    if bundle.get("needs_dense"):
        X_shared = np.asarray(X_shared.todense(), dtype=np.float32)

    proba = np.asarray(classifier.predict_proba(X_shared))
    pred_idx = np.argmax(proba, axis=1)
    return {
        "predicted_label": label_encoder.inverse_transform(pred_idx).tolist(),
        "confidence": proba[np.arange(len(pred_idx)), pred_idx].tolist(),
        "class_names": list(label_encoder.classes_),
        "probabilities": proba.tolist(),
    }


def predict_bp3(bundle: dict[str, Any], X_raw: pd.DataFrame) -> dict[str, Any]:
    """Run BP3's persisted one-hot + company-frequency + xgboost bundle end to end: a raw feature
    DataFrame (columns = bundle['feature_cols_categorical'] + [bundle['company_col']]) in,
    predicted binary escalation label (0/1) + probability-of-escalation + full 2-column
    probability array out. An unseen company at inference time gets frequency 0 - never
    fabricated, the exact same fallback rule Gates 3/4/5 already use for a test-set company absent
    from the train-fit frequency map (never inference/test-set-derived). BP3's real pipeline never
    fits a LabelEncoder (its target is already binary 0/1 - see the module docstring), so unlike
    predict_bp1()/predict_bp2() this function reads class_names directly off the bundle rather
    than off a label_encoder.classes_ attribute, and predicted_label is the raw 0/1 int the
    classifier's own predict_proba() argmax picks - not an inverse-transformed label."""
    if bundle.get("bp_id") != "bp3":
        raise ValueError(
            f"predict_bp3() called on a bundle with bp_id={bundle.get('bp_id')!r}, expected 'bp3'."
        )
    preprocessor = bundle["preprocessor"]
    company_freq_map = bundle["company_freq_map"]
    company_col = bundle["company_col"]
    classifier = bundle["classifier"]
    class_names = bundle["class_names"]

    X_ohe = preprocessor.transform(X_raw)
    freq = X_raw[company_col].map(company_freq_map).fillna(0).to_numpy(dtype=np.float32).reshape(-1, 1)
    X_shared = sp.hstack([X_ohe, sp.csr_matrix(freq)], format="csr")
    if bundle.get("needs_dense"):
        X_shared = np.asarray(X_shared.todense(), dtype=np.float32)

    proba = np.asarray(classifier.predict_proba(X_shared))
    pred_idx = np.argmax(proba, axis=1)
    return {
        "predicted_label": pred_idx.tolist(),
        "probability_positive_class": proba[:, 1].tolist(),
        "confidence": proba[np.arange(len(pred_idx)), pred_idx].tolist(),
        "class_names": list(class_names),
        "probabilities": proba.tolist(),
    }
