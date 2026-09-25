"""
src/models/bp1_intent_classifier.py — Customer360 Navigator

BP1 (Customer Intent Classification) shared model-pipeline definitions, extracted for BP1 Gate 6
(Productization, Monitoring & Governance) as a HYPER hardening fix.

Why this module exists: BP1 Gates 3, 4, and 5 (already real-run confirmed) each independently
define an identical TF-IDF + candidate-model pipeline inline, because notebooks are the unit of
delivery for this project (Claude generates notebooks; the user runs them; nothing Claude
generates is executed by Claude itself). Each of those three notebooks' own docstrings already
flags this duplication as a "single-source-of-truth risk," guarded only by a live consistency
check (e.g. Gate 4/5 re-deriving a metric and comparing it back to Gate 3's recorded value).

This module does NOT retroactively change Gates 3, 4, or 5 - those notebooks remain exactly as
delivered and already real-run confirmed; editing them now would mean re-running already-closed,
verified work for no functional gain. This module exists so that (a) the pipeline-construction
logic has one real, unit-testable, importable definition for Gate 6's pytest coverage and (b) any
future BP1 work (or a future BP that reuses the same TF-IDF + classical-ML pattern) can import
from here instead of re-duplicating the dict a fourth time.

The definitions below are a byte-for-byte match of what Gates 3/4/5 define inline - verified by
this module's own test suite comparing its constants against the literal values used in those
notebooks' source.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

TFIDF_KWARGS: dict[str, Any] = dict(
    max_features=5000,
    ngram_range=(1, 2),
    min_df=2,
    sublinear_tf=True,
    stop_words="english",
)

NEEDS_DENSE: frozenset[str] = frozenset({"hist_gradient_boosting"})


def make_candidates(random_state: int) -> dict[str, Any]:
    """Return the 6-model candidate dict used by BP1 Gate 3's benchmark (and re-derived by
    Gates 4/5), parameterized by the project's configured random_state (never hardcoded - reads
    from configs/bp1_customer_intent_classification.yaml's random_state, same as every gate
    notebook already does). Internal thread counts are fixed at 1/single-threaded by design (WARP
    - no nested parallelism; the outer CV loop is where parallelism, if any, is applied).
    """
    from catboost import CatBoostClassifier
    from lightgbm import LGBMClassifier
    from xgboost import XGBClassifier

    return {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=random_state),
        "random_forest": RandomForestClassifier(
            n_estimators=100, max_depth=20, n_jobs=1, random_state=random_state
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=100, random_state=random_state),
        "xgboost": XGBClassifier(
            n_estimators=100,
            max_depth=6,
            n_jobs=1,
            verbosity=0,
            random_state=random_state,
        ),
        "lightgbm": LGBMClassifier(n_estimators=100, n_jobs=1, verbose=-1, random_state=random_state),
        "catboost": CatBoostClassifier(
            iterations=100,
            thread_count=1,
            verbose=False,
            allow_writing_files=False,
            random_state=random_state,
        ),
    }


def to_dense(x):
    """Densify a sparse matrix for estimators that reject sparse input at fit time
    (HistGradientBoostingClassifier) - a no-op for anything already dense."""
    return x.toarray() if hasattr(x, "toarray") else x


def make_pipeline(name: str, candidates: dict[str, Any]) -> Pipeline:
    """Build the TF-IDF -> [densify if needed] -> classifier pipeline for one named candidate.
    `candidates` is passed in (rather than constructed here) so callers reuse ONE fitted-state-
    free candidate dict across CV folds without accidentally sharing a fitted estimator instance
    between folds - callers should call make_candidates() fresh per pipeline construction, exactly
    as Gates 3/4/5 do inline."""
    if name not in candidates:
        raise KeyError(f"Unknown candidate '{name}'. Known candidates: {sorted(candidates.keys())}")
    steps = [("tfidf", TfidfVectorizer(**TFIDF_KWARGS))]
    if name in NEEDS_DENSE:
        steps.append(("densify", FunctionTransformer(to_dense, accept_sparse=True)))
    steps.append(("clf", candidates[name]))
    return Pipeline(steps)


def reason_codes_for_row(
    row_shap_values: np.ndarray,
    row_tfidf_weights: np.ndarray,
    feature_names: np.ndarray,
    n_reason_codes: int = 5,
) -> list[str]:
    """BP1 Gate 5's reason-code grounding rule, extracted for unit testing: a reason code is only
    ever drawn from a feature whose TF-IDF weight in THIS row is nonzero - i.e. a term literally
    present in that row's own text by construction of the vectorizer, not asserted after the
    fact. Returns up to n_reason_codes feature names, ranked by |SHAP value| among only the
    grounded (nonzero-weight) candidates."""
    if row_shap_values.shape != row_tfidf_weights.shape:
        raise ValueError(
            f"Shape mismatch: shap values {row_shap_values.shape} vs tfidf weights {row_tfidf_weights.shape}"
        )
    nonzero_mask = row_tfidf_weights != 0.0
    if not nonzero_mask.any():
        return []
    masked_shap = np.where(nonzero_mask, np.abs(row_shap_values), -np.inf)
    top_k = min(n_reason_codes, int(nonzero_mask.sum()))
    top_idx = np.argsort(masked_shap)[::-1][:top_k]
    return [str(feature_names[i]) for i in top_idx]
