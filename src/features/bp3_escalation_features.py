"""
src/features/bp3_escalation_features.py — Customer360 Navigator

BP3 (Complaint Escalation / Intervention Prediction) shared feature-engineering module, built at
Gate 2 (Data Verification & Feature/Taxonomy Engineering) rather than triplicated inline across
Gates 3/4/5 first and only centralized retroactively at Gate 6 - the exact technical debt BP2 hit
and fixed after the fact (see src/features/bp2_friction_features.py's own docstring). Building it
now (HYPER: shared component library, built once) avoids repeating that mistake for BP3.

Why BP3's Gate 2 differs from BP1's and BP2's: BP1 Gate 2 built a CFPB<->BANKING77 crosswalk
(taxonomy_mapper.py) and BP2 Gate 2 built a severity bucket-to-class mapping
(friction_severity_mapper.py) - both required a genuinely new judgment-based taxonomy. BP3's
target (`intervention_required`) was already fully and unambiguously defined at Gate 1 directly
from one real CFPB field's literal values (no bucket-to-class judgment mapping needed), and BP3
does not integrate BANKING77 at all (Master Plan BP table: Integrates BANKING77? = NO). So this
module's Gate 2 job is the two things Gate 2's own exit criteria actually require here: zero nulls
silently dropped in the real candidate feature columns, and a complete feature-lineage table -
plus tagging every real row with its target/exclusion status and writing the Gold layer,
mirroring BP2 Gate 2's "every row tagged, none dropped" pattern.

Gate 6 addition (2026-09-23, HYPER hardening fix - mirrors BP2 Gate 6's own extraction of
src/features/bp2_friction_features.py, for the identical single-source-of-truth reason): unlike
BP2, BP3's Gate 2 already centralized the feature-lineage/null-handling logic above, so the ONLY
duplication BP3 Gates 3/4/5 actually carry is the 5-model CANDIDATES dict and the shared one-hot +
frequency preprocessing pipeline, each independently re-declared inline in all three delivered,
already real-run-confirmed notebooks. This module is extended (not replaced) with that missing
piece below - `make_candidates()`, `build_shared_preprocessing()`, `to_dense()`,
`is_linear_champion()` - so Gate 6's pytest suite has a real, importable, unit-tested definition
to cover, and any future BP3 work has one source of truth instead of a fourth inline copy. This
extension does NOT retroactively change Gates 3, 4, or 5 - those notebooks remain exactly as
delivered and already real-run confirmed (champion=xgboost, held-out test PR-AUC=0.3496); editing
them now would mean re-running already-closed, verified work for no functional gain. BP3 never
had a raw-categorical (CatBoost) candidate (Lesson #22, user's top-5-models instruction), so unlike
bp2_friction_features.py this module needs no CATBOOST_FEATURE_COLS / USES_RAW_CATEGORICAL /
reason_codes_for_row_raw_categorical / reorder_predict_proba - unlike BP2, that path genuinely
never existed here, not simply unused.

Standing rules this module follows:
  - WARP: Polars lazy scans, category dtype (reused from taxonomy_mapper.CFPB_DTYPES, not
    re-derived), no pandas, no eager full-file loads where a lazy scan + select + collect will do
    (Gate-2-era functions only - the Gate-6-added pipeline functions below operate on already
    in-memory pandas/sparse arrays, matching Gates 3/4/5's own real notebook code exactly).
  - Zero-fabrication: every null count, distinct-value count, and row-accounting number this
    module's report functions produce is computed live against the real CFPB file - none are
    asserted from DATA_PROFILE_REPORT.md or policy.json without re-measuring.
  - This module is import-only shared logic (HYPER). It performs no I/O side effects at import
    time and is never executed by Claude - only the user runs it, per the execution-boundary rule.

Public functions:
  intervention_target_expr()                          -> list[pl.Expr]
  null_screen_report(cfpb_lazy)                        -> pl.DataFrame
  fill_categorical_nulls_expr()                        -> list[pl.Expr]
  load_cfpb_with_target_and_filled_features(cfpb_path) -> pl.LazyFrame
  feature_lineage_table()                              -> pl.DataFrame
  build_bp3_escalation_gold_layer(cfpb_lazy, out_dir)  -> dict (paths + row counts)
  make_candidates(random_state, scale_pos_weight)      -> dict[str, Any]              (Gate 6)
  build_shared_preprocessing(X_train_raw, X_test_raw)  -> tuple                       (Gate 6)
  to_dense(x)                                          -> np.ndarray                  (Gate 6)
  is_linear_champion(champion_model)                   -> bool                        (Gate 6)
  reason_codes_for_row_shared                          -> re-exported from BP1        (Gate 6)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from scipy import sparse as sp
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

from taxonomy.taxonomy_mapper import CFPB_DTYPES  # noqa: F401  (re-exported for callers)

# BP1's already-tested nonzero-weight reason-code grounding rule, reused verbatim (HYPER) - the
# exact rule Gate 5's own inline nonzero-value masking logic already implements (only report a
# feature whose value in a given row is nonzero); re-exported here so Gate 6's pytest suite has a
# single, importable, unit-tested definition to cover, matching bp2_friction_features.py's pattern.
from models.bp1_intent_classifier import reason_codes_for_row as reason_codes_for_row_shared  # noqa

# Barred from the engineered feature set entirely - defines the target, or a leakage/compliance
# risk documented in BP3 Gate 1's policy.json leakage_rules (see that artifact for the real,
# per-column rationale - not re-derived here).
BARRED_COLUMNS: list[str] = [
    "Company response to consumer",
    "Timely response?",
    "Date received",
    "Date sent to company",
    "Tags",
    "Complaint ID",
    "ZIP code",
]

# The 6 real, low/medium-cardinality categorical candidate feature columns (one-hot at Gate 3),
# per BP3 Gate 1's policy.json feature_variable_candidates. Company (2,970 distinct, per
# DATA_PROFILE_REPORT.md) is handled separately below (frequency-encoded, not one-hot - identical
# design choice to bp2_friction_features.py's COMPANY_COL, HYPER reuse of the same pattern).
FEATURE_COLS_CATEGORICAL: list[str] = [
    "Product",
    "Sub-product",
    "Issue",
    "Sub-issue",
    "State",
    "Submitted via",
]
COMPANY_COL: str = "Company"

# Explicit per-column sentinel for real nulls found in the candidate feature columns
# (DATA_PROFILE_REPORT.md, re-verified live in this notebook's own Section 6) - Gate 2's own exit
# criterion is "zero nulls silently dropped," so every null-bearing candidate column gets its own
# named sentinel category (traceable back to its source column in feature_lineage_table() below)
# rather than a generic "MISSING" or an implicit drop/error from a downstream OneHotEncoder.
# Product/Issue/Submitted via/Company have 0 real nulls (DATA_PROFILE_REPORT.md) and need no
# sentinel - listed here only for the columns that actually have one.
NULL_SENTINEL_MAP: dict[str, str] = {
    "Sub-product": "MISSING_SUB_PRODUCT",
    "Sub-issue": "MISSING_SUB_ISSUE",
    "State": "MISSING_STATE",
}


def intervention_target_expr() -> list[pl.Expr]:
    """BP3 Gate 1's target rule (policy.json target_definition), as Polars expressions:
    `intervention_required` (Int8, null for excluded rows) and `exclusion_reason` (Utf8, null for
    trainable rows). Must match Gate 1's documented rule exactly - never re-derived differently
    here."""
    intervention_required = (
        pl.when(pl.col("Company response to consumer") == "Closed with monetary relief")
        .then(pl.lit(1, dtype=pl.Int8))
        .when(
            pl.col("Company response to consumer").is_in(
                ["Closed with explanation", "Closed with non-monetary relief"]
            )
        )
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.lit(None, dtype=pl.Int8))
        .alias("intervention_required")
    )
    exclusion_reason = (
        pl.when(pl.col("Company response to consumer") == "In progress")
        .then(pl.lit("EXCLUDED_PENDING"))
        .when(pl.col("Company response to consumer") == "Untimely response")
        .then(pl.lit("EXCLUDED_UNTIMELY_RESPONSE_OVERLAPS_BP2"))
        .when(pl.col("Company response to consumer").is_null())
        .then(pl.lit("EXCLUDED_UNKNOWN_NULL_RESPONSE"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("exclusion_reason")
    )
    return [intervention_required, exclusion_reason]


def null_screen_report(cfpb_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Live null count for every BP3 candidate feature column (FEATURE_COLS_CATEGORICAL +
    COMPANY_COL) - the real numbers Gate 2's 'zero nulls silently dropped' exit criterion is
    checked against, computed fresh rather than trusted from DATA_PROFILE_REPORT.md."""
    cols = FEATURE_COLS_CATEGORICAL + [COMPANY_COL]
    wide = cfpb_lazy.select([pl.col(c).is_null().sum().alias(c) for c in cols]).collect()
    return pl.DataFrame({"column": cols, "null_count": [int(wide[c][0]) for c in cols]})


def fill_categorical_nulls_expr() -> list[pl.Expr]:
    """Explicit sentinel fill for every candidate feature column with a documented real null count
    (NULL_SENTINEL_MAP) - satisfies Gate 2's 'zero nulls silently dropped' exit criterion. A
    column with a real null count of 0 does not need (and is not given) a no-op fill here."""
    return [
        pl.col(col).cast(pl.Utf8).fill_null(sentinel).cast(pl.Categorical).alias(col)
        for col, sentinel in NULL_SENTINEL_MAP.items()
    ]


def load_cfpb_with_target_and_filled_features(cfpb_path: str | Path) -> pl.LazyFrame:
    """Lazy-scan the CFPB complaints file (WARP: no eager full-file load), attach
    `intervention_required` + `exclusion_reason` (this module's own target rule, matching Gate 1's
    policy.json exactly), and apply the explicit null-sentinel fill to every candidate feature
    column that has one - never a silent drop."""
    lazy = pl.scan_csv(cfpb_path, schema_overrides=CFPB_DTYPES)
    lazy = lazy.with_columns(intervention_target_expr())
    lazy = lazy.with_columns(fill_categorical_nulls_expr())
    return lazy


def feature_lineage_table() -> pl.DataFrame:
    """The feature-lineage table Gate 2's own exit criterion requires ('feature-lineage table
    complete') - one row per engineered feature, its real source column, and its transform. Built
    from this module's own constants (never hand-duplicated elsewhere) so it can never drift from
    what the pipeline actually does."""
    rows: list[dict] = []
    for col in FEATURE_COLS_CATEGORICAL:
        sentinel = NULL_SENTINEL_MAP.get(col)
        rows.append(
            {
                "engineered_feature": f"{col} (one-hot, Gate 3)",
                "source_column": col,
                "transform": "one-hot encoding (fit on train only, Gate 3)",
                "null_handling": (
                    f"real nulls filled with sentinel category '{sentinel}'"
                    if sentinel
                    else "no real nulls in this column (DATA_PROFILE_REPORT.md, re-verified live)"
                ),
            }
        )
    rows.append(
        {
            "engineered_feature": "Company_freq",
            "source_column": COMPANY_COL,
            "transform": (
                "frequency encoding (fit on train only; unseen test-time companies get "
                "frequency 0 - never fabricated, never test-set-derived)"
            ),
            "null_handling": "no real nulls in this column (DATA_PROFILE_REPORT.md, re-verified live)",
        }
    )
    rows.append(
        {
            "engineered_feature": "intervention_required (TARGET, not a feature)",
            "source_column": "Company response to consumer",
            "transform": "binary target rule per Gate 1 policy.json - never used as an input feature",
            "null_handling": "n/a - this is the label, not an input feature",
        }
    )
    for barred_col in BARRED_COLUMNS:
        rows.append(
            {
                "engineered_feature": "(none - barred)",
                "source_column": barred_col,
                "transform": "EXCLUDED from the feature set entirely - see Gate 1 policy.json leakage_rules",
                "null_handling": "n/a - column is never read into any engineered feature",
            }
        )
    return pl.DataFrame(rows)


def build_bp3_escalation_gold_layer(cfpb_lazy: pl.LazyFrame, out_dir: str | Path) -> dict:
    """Write the BP3 CFPB-with-target Gold layer to Parquet (WARP) - every real row tagged with
    intervention_required/exclusion_reason, none dropped here (mirrors BP2 Gate 2's
    build_bp2_severity_gold_layer pattern exactly; filtering to the trainable subset is a Gate 3
    decision, not made here)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gold_path = out_dir / "cfpb_intervention_escalation_gold.parquet"
    cfpb_lazy.sink_parquet(gold_path)
    rows_written = pl.scan_parquet(gold_path).select(pl.len()).collect().item()

    return {
        "cfpb_escalation_gold_path": str(gold_path),
        "cfpb_escalation_gold_rows_written": rows_written,
    }


# =============================================================================
# Gate 6 addition (2026-09-23): the CANDIDATES dict + shared preprocessing pipeline Gates 3/4/5
# each independently declare inline - extracted here as the single source of truth, mirroring
# bp2_friction_features.py's own equivalent extraction. See module docstring "Gate 6 addition" note
# above for why this is the only piece of BP3's pipeline that still needed extracting.
# =============================================================================

NEEDS_DENSE: frozenset[str] = frozenset({"hist_gradient_boosting"})


def make_candidates(random_state: int, scale_pos_weight: float) -> dict[str, Any]:
    """Return the 5-model candidate dict used by BP3 Gate 3's benchmark (and re-derived, per-fold,
    by Gates 4/5), parameterized by the project's configured random_state and the LIVE
    scale_pos_weight computed from the real train split's class balance (Gates 3/4/5 each compute
    this the same way: n_train_negative / n_train_positive - never a remembered constant, since it
    depends on the exact train split). class_weight='balanced' is applied wherever this
    environment's real installed library API supports it - HistGradientBoostingClassifier's
    sklearn API does not expose an equivalent (the same documented library-capability asymmetry
    bp2_friction_features.py's make_candidates() already notes); XGBoost instead receives the
    live-computed scale_pos_weight, its own native imbalance-compensation parameter, which
    class_weight='balanced' would not affect for XGBoost's sklearn API.

    BP3 never had a CatBoost/raw-categorical candidate (Lesson #22, user's top-5-models
    instruction) - unlike bp2_friction_features.py's make_candidates(), there is no removal note
    here because that path never existed for this BP."""
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
            scale_pos_weight=scale_pos_weight,
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
    """Fit the shared one-hot (6 low-cardinality categorical columns) + frequency-encoded
    (Company, 2,970 distinct real values - too high-cardinality to one-hot) preprocessing on TRAIN
    only, exactly as Gates 3/4/5 each define inline (fit on train, unseen companies at test time
    get frequency 0 - never fabricated, never test-set-derived). Returns (ohe, X_train_shared,
    X_test_shared, company_freq_map, feature_names) - feature_names is the OHE's own output names
    plus "Company_freq", the exact array Gate 4/5's SHAP feature-name assembly builds inline."""
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
    """Densify a sparse matrix for estimators that reject sparse input outright
    (hist_gradient_boosting at fit time; every tree-based champion's shap.TreeExplainer call, per
    BP1/BP2/BP3 Gate 4's real-environment finding) - a no-op for anything already dense.
    Byte-for-byte the same helper BP1's and BP2's to_dense() implement; re-declared here rather
    than imported so this module has no cross-BP import dependency for its own core preprocessing
    path (the one deliberate cross-BP import, reason_codes_for_row_shared above, is called out
    explicitly)."""
    return x.toarray() if hasattr(x, "toarray") else x


def is_linear_champion(champion_model) -> bool:
    """The exact SHAP-explainer-selection / densification-gating rule BP1/BP2 Gate 4 fixed a real
    bug over before delivery, and BP3 Gates 4/5 already apply inline: densify (and use
    TreeExplainer) whenever the champion is NOT LogisticRegression - never gated on Gate 3's
    fit-time-only NEEDS_DENSE set. This environment's real shap.TreeExplainer.shap_values()
    rejects sparse input for every tree-based candidate, not only NEEDS_DENSE members
    (NEEDS_DENSE is a FIT-time-only constraint, a different scope)."""
    return isinstance(champion_model, LogisticRegression)
