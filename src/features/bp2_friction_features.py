"""
src/features/bp2_friction_features.py — Customer360 Navigator

BP2 (Customer Friction Classification) shared feature-engineering + model-pipeline definitions,
extracted for BP2 Gate 6 (Productization, Monitoring & Governance) as a HYPER hardening fix -
mirrors BP1 Gate 6's own extraction of src/models/bp1_intent_classifier.py, for the identical
reason and under the identical constraint.

Why this module exists: BP2 Gates 3, 4, and 5 (all real-run confirmed on the user's machine) each
independently define an identical structured-feature preprocessing pipeline inline (one-hot +
frequency-encoded "shared" path for 5 of 6 candidates; CatBoost's own raw-categorical path) and an
identical 6-model candidate dict, because notebooks are this project's unit of delivery (Claude
generates notebooks; the user runs them for real; Claude never executes the pipeline itself). Each
of those three notebooks' own section comments already flags this duplication as intentional and
guards it only with live consistency checks (e.g. Gate 4/5 re-deriving a metric and comparing it
back to Gate 3's recorded value) - the exact single-source-of-truth risk BP1 Gate 6 already fixed
once, for BP1's own TF-IDF pipeline.

This module does NOT retroactively change Gates 3, 4, or 5 - those notebooks remain exactly as
delivered and already real-run confirmed (champion=xgboost, held-out f1_macro=0.4559); editing
them now would mean re-running already-closed, verified work for no functional gain. This module
exists so that (a) the pipeline-construction and reason-code-grounding logic has one real,
unit-testable, importable definition for Gate 6's pytest coverage, and (b) any future BP2 work (or
a future BP reusing this structured-feature + raw-categorical pattern) can import from here instead
of duplicating the dict a fourth time.

The constants and hyperparameters below are a byte-for-byte match of what Gates 3/4/5 define
inline - verified by this module's own test suite comparing them against the literal values those
notebooks' delivered source uses.

Reuse note (HYPER, cross-BP): per-row reason-code grounding for the shared one-hot/frequency
feature space uses the EXACT same nonzero-weight-masking rule BP1's `reason_codes_for_row`
(src/models/bp1_intent_classifier.py) already implements and already has full pytest coverage for
- imported and reused here UNMODIFIED (see `reason_codes_for_row_shared` below) rather than
re-implemented, since the rule ("only report a feature whose value in this row is nonzero") is
identical whether "nonzero" means a TF-IDF weight (BP1) or a one-hot/frequency feature value (BP2).
Only CatBoost's raw-categorical path (no "absent" concept - every column always holds a real
value) needed a genuinely new function, `reason_codes_for_row_raw_categorical`, below.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse as sp
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

# BP1's already-tested nonzero-weight reason-code grounding rule, reused verbatim (HYPER) - see
# module docstring "Reuse note" above.
from models.bp1_intent_classifier import reason_codes_for_row as reason_codes_for_row_shared  # noqa

# ---------------------------------------------------------------------------
# Feature-column constants - must exactly match what Gates 3/4/5 define inline.
# ---------------------------------------------------------------------------
FEATURE_COLS_CATEGORICAL: list[str] = [
    "Product",
    "Sub-product",
    "Issue",
    "Sub-issue",
    "State",
    "Submitted via",
    "common_taxonomy_bucket",
]
COMPANY_COL: str = "Company"
CATBOOST_FEATURE_COLS: list[str] = FEATURE_COLS_CATEGORICAL + [COMPANY_COL]

BARRED_COLUMNS: list[str] = [
    "Company response to consumer",
    "Timely response?",
    "Date received",
    "Date sent to company",
    "Company public response",
    "Complaint ID",
    "ZIP code",
    "Tags",
]

NEEDS_DENSE: frozenset[str] = frozenset({"hist_gradient_boosting"})
# Empty since 2026-09-22 - CatBoost (the only candidate that ever used this path) was removed
# from make_candidates() below; see Lesson #22 in LESSONS_LEARNED_APPLIED.md for why, and the
# make_candidates() docstring for the removal note. Kept as a named symbol (not deleted outright)
# since reason_codes_for_row_raw_categorical/reorder_predict_proba below remain available,
# already-tested infrastructure for any future BP/candidate that needs a raw-categorical path.
USES_RAW_CATEGORICAL: frozenset[str] = frozenset()


def make_candidates(random_state: int) -> dict[str, Any]:
    """Return the 5-model candidate dict used by BP2 Gate 3's benchmark (and re-derived, per-fold,
    by Gates 4/5), parameterized by the project's configured random_state. class_weight='balanced'
    is applied wherever this environment's real installed library API supports it for multiclass -
    HistGradientBoostingClassifier and XGBoost's sklearn API do not expose an equivalent, a
    documented library-capability asymmetry carried over unchanged from Gates 3/4/5, not an
    oversight here.

    CatBoost removed 2026-09-22 (user decision, after Lesson #22 in LESSONS_LEARNED_APPLIED.md
    root-caused a real scikit-learn 1.8.0 clone() incompatibility with CatBoost's cat_features
    constructor argument - see that lesson for the full sandbox-reproduced diagnosis). This
    module's raw-categorical helpers (CATBOOST_FEATURE_COLS, reason_codes_for_row_raw_categorical,
    reorder_predict_proba) are deliberately kept as general-purpose, already-tested infrastructure
    for any future candidate that needs a raw-categorical path - they are simply unused by BP2's
    candidate set now."""
    from lightgbm import LGBMClassifier
    from xgboost import XGBClassifier

    return {
        "logistic_regression": LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=random_state
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            class_weight="balanced",
            n_jobs=1,
            random_state=random_state,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=100, random_state=random_state),
        "xgboost": XGBClassifier(
            n_estimators=100,
            max_depth=6,
            n_jobs=1,
            verbosity=0,
            random_state=random_state,
        ),
        "lightgbm": LGBMClassifier(
            n_estimators=100,
            class_weight="balanced",
            n_jobs=1,
            verbose=-1,
            random_state=random_state,
        ),
    }


def build_shared_preprocessing(X_train_raw: pd.DataFrame, X_test_raw: pd.DataFrame):
    """Fit the shared one-hot (7 low-cardinality categorical columns) + frequency-encoded
    (Company, 2,970 distinct real values - too high-cardinality to one-hot) preprocessing on TRAIN
    only, exactly as Gates 3/4/5 each define inline (fit on train, unseen companies at test time
    get frequency 0 - never fabricated, never test-set-derived). Returns (ohe, X_train_shared,
    X_test_shared, company_freq_map, feature_names) - feature_names is the OHE's own output names
    plus "Company_freq", the exact array Gate 4/5's SHAP feature-name assembly builds inline.
    """
    ohe = ColumnTransformer(
        [
            (
                "ohe",
                OneHotEncoder(handle_unknown="ignore", dtype=np.float32),
                FEATURE_COLS_CATEGORICAL,
            )
        ],
        remainder="drop",
    )
    X_train_ohe = ohe.fit_transform(X_train_raw)
    X_test_ohe = ohe.transform(X_test_raw)

    company_freq_map = X_train_raw[COMPANY_COL].value_counts().to_dict()
    train_company_freq = (
        X_train_raw[COMPANY_COL].map(company_freq_map).fillna(0).to_numpy(dtype=np.float32).reshape(-1, 1)
    )
    test_company_freq = (
        X_test_raw[COMPANY_COL].map(company_freq_map).fillna(0).to_numpy(dtype=np.float32).reshape(-1, 1)
    )

    X_train_shared = sp.hstack([X_train_ohe, sp.csr_matrix(train_company_freq)], format="csr")
    X_test_shared = sp.hstack([X_test_ohe, sp.csr_matrix(test_company_freq)], format="csr")
    feature_names = np.array(list(ohe.get_feature_names_out()) + ["Company_freq"])
    return ohe, X_train_shared, X_test_shared, company_freq_map, feature_names


def to_dense(x):
    """Densify a sparse matrix for estimators that reject sparse input outright (hist_gradient_
    boosting at fit time; every tree-based champion's shap.TreeExplainer call, per BP1/BP2 Gate 4's
    real-environment finding) - a no-op for anything already dense. Byte-for-byte the same helper
    BP1's to_dense() implements; re-declared here rather than imported from bp1_intent_classifier
    so this module has no BP1 import dependency for its own core preprocessing path (the one
    deliberate cross-BP import, reason_codes_for_row_shared above, is called out explicitly).
    """
    return x.toarray() if hasattr(x, "toarray") else x


def is_linear_champion(champion_model) -> bool:
    """The exact SHAP-explainer-selection / densification-gating rule BP2 Gate 4 fixed a real bug
    over before delivery: densify (and use TreeExplainer) whenever the champion is NOT
    LogisticRegression - never gated on Gate 3's fit-time-only NEEDS_DENSE set. This environment's
    real shap.TreeExplainer.shap_values() rejects sparse input for every tree-based candidate, not
    only NEEDS_DENSE members (NEEDS_DENSE is a FIT-time-only constraint, a different scope).
    """
    return isinstance(champion_model, LogisticRegression)


def reorder_predict_proba(champion_model, y_proba_raw, label_encoder) -> np.ndarray:
    """The predict_proba column-reordering fix introduced in BP2 Gate 4 (not present in BP1 Gate 4,
    since BP1 never had a raw-categorical champion): a raw-categorical model's (e.g. CatBoost)
    `classes_` attribute is the model's OWN discovered class order, which is not guaranteed to
    match `label_encoder.classes_`'s integer-encoded order - reorder the probability columns to
    match label_encoder's order before computing ROC-AUC or writing decision records/confidence
    scores. Returns the reordered array (identity reorder if the orders already match).
    """
    proba_classes = list(champion_model.classes_)
    proba_order = [proba_classes.index(c) for c in label_encoder.classes_]
    return np.asarray(y_proba_raw)[:, proba_order]


def reason_codes_for_row_raw_categorical(
    row_shap_values: np.ndarray,
    feature_names: np.ndarray,
    row_values: pd.Series,
    n_reason_codes: int = 5,
) -> list[str]:
    """BP2 Gate 5's raw-categorical (CatBoost) reason-code rule: every column always holds a real
    value (MISSING is itself a valid category - no "absent" concept the way a one-hot/TF-IDF
    feature has), so every feature is eligible, and codes are formatted as "Column=Value" to stay
    self-descriptive on their own - the same standard the one-hot column names already provide "for
    free" via their own naming. Ranked by |SHAP value|, top n_reason_codes."""
    if row_shap_values.shape != feature_names.shape:
        raise ValueError(
            f"Shape mismatch: shap values {row_shap_values.shape} vs feature names {feature_names.shape}"
        )
    top_k = min(n_reason_codes, len(feature_names))
    top_idx = np.argsort(np.abs(row_shap_values))[::-1][:top_k]
    return [f"{feature_names[j]}={row_values[feature_names[j]]}" for j in top_idx]
