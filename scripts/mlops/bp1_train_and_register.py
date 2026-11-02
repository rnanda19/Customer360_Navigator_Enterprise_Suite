"""
scripts/mlops/bp1_train_and_register.py — Customer360 Navigator

PHASE D: the one real, end-to-end MLflow-tracked training + Model Registry registration run this
project performs, demonstrated on BP1 (Customer Intent Classification) because it is the only BP
whose real champion pipeline (src/models/bp1_intent_classifier.py's make_pipeline()) is a fast,
standalone, already-unit-tested fit over a small real dataset (BANKING77: 10,016 train / 3,084
test rows, ~1MB total) that this environment can actually run end to end - unlike BP2-BP8, whose
champions are fit over the real CFPB extract (a 322MB file that lives outside this repository by
design, per data/.gitignore, and were not re-fit in this Phase D pass; see MLOPS_ARCHITECTURE.md
and the Phase D final delivery report for the explicit disclosure of that boundary).

This script performs the REAL thing end to end:
    1. Load the real BANKING77 train/test CSVs from --data-dir (never fabricated rows).
    2. Fit the real champion pipeline (TF-IDF + LogisticRegression, random_state=42, the exact
       same src.models.bp1_intent_classifier.make_pipeline() construction BP1 Gates 3/4/5 and the
       original Hardening Step 2 model-persistence notebook already used).
    3. Evaluate on the real held-out BANKING77 test split (never re-randomized - same rule BP1's
       own config.yaml leakage_rules already state).
    4. Log real params/metrics/dataset-fingerprint/git-SHA/software-versions to MLflow
       (src/mlops/tracking.py) under experiment "customer360_bp1_customer_intent_classification".
    5. Save the real fitted bundle via src/models/model_persistence.py's save_model_bundle() (the
       exact same bundle shape/contract BP1's inference service already expects) and log it as an
       MLflow run artifact.
    6. Register the run's model as a new version of the "customer360_bp1" registered model
       (src/mlops/registry.py), tagged with real provenance + real metrics.

Nothing here is simulated: the accuracy/F1 numbers reported are computed by sklearn against the
real test split, and are expected to closely match (not necessarily bit-for-bit, since this is an
independent fresh fit, not a replay) the historically recorded
configs/bp1_customer_intent_classification.yaml gate3/gate5 values (0.8224 accuracy) - the script
prints both for direct comparison and does not edit that config file.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402
from sklearn.preprocessing import LabelEncoder  # noqa: E402

from mlops import registry, tracking  # noqa: E402
from models.bp1_intent_classifier import make_pipeline  # noqa: E402
from models.model_persistence import save_model_bundle  # noqa: E402

EXPERIMENT_NAME = "customer360_bp1_customer_intent_classification"
CHAMPION_NAME = "logistic_regression"


def load_banking77(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_path = data_dir / "banking77_train.csv"
    test_path = data_dir / "banking77_test.csv"
    if not train_path.exists() or not test_path.exists():
        raise FileNotFoundError(
            f"Real BANKING77 CSVs not found under {data_dir} - expected banking77_train.csv and "
            f"banking77_test.csv (this script never fabricates training data)."
        )
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)
    return train_df, test_df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing banking77_train.csv and banking77_test.csv",
    )
    parser.add_argument("--mlruns-dir", type=Path, default=tracking.DEFAULT_MLRUNS_DIR)
    parser.add_argument(
        "--models-dir", type=Path, default=REPO_ROOT / "models" / "bp1_customer_intent_classification"
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help=(
            "Candidate variant for a genuine (non-fabricated) challenger run - "
            "a different real refit, not a copy of the champion."
        ),
    )
    parser.add_argument(
        "--run-name-suffix",
        type=str,
        default="",
        help="Appended to the MLflow run_name, e.g. '_challenger_v2'.",
    )
    parser.add_argument(
        "--max-train-rows",
        type=int,
        default=None,
        help=(
            "Deliberately truncate the real training set to this many rows - for "
            "producing a genuinely weaker (never fabricated) candidate to demonstrate "
            "governance rejection, not a synthetic metric."
        ),
    )
    args = parser.parse_args()
    random_state = args.random_state

    train_df, test_df = load_banking77(args.data_dir)
    print(
        f"Loaded real BANKING77 data: train={len(train_df)} rows, test={len(test_df)} rows "
        f"from {args.data_dir}"
    )

    if args.max_train_rows is not None:
        # Stratified per-class truncation (not a positional slice) - the real CSV is grouped by
        # category, so a plain head(N) would drop entire classes and crash the label encoder on
        # unseen test labels. groupby().head(k) keeps every real class represented, just with
        # genuinely fewer real examples per class - a real, not fabricated, weaker-data scenario.
        per_class = max(1, args.max_train_rows // train_df["category"].nunique())
        train_df = (
            train_df.groupby("category", group_keys=False)
            .apply(lambda g: g.head(per_class))
            .reset_index(drop=True)
        )
        print(
            f"NOTE: --max-train-rows stratified-truncated the real training set to "
            f"{len(train_df)} rows ({per_class}/class) - demonstration of a genuinely "
            f"weaker candidate, not a fabricated metric."
        )

    label_encoder = LabelEncoder()
    y_train = label_encoder.fit_transform(train_df["category"])
    y_test = label_encoder.transform(test_df["category"])

    # Build ONLY the real champion candidate (logistic_regression), not the full 6-model
    # make_candidates() dict - BP1's benchmark across all 6 candidates is already real-run
    # confirmed (Gates 3/4/5; see configs/bp1_customer_intent_classification.yaml), and this
    # environment does not have xgboost/lightgbm/catboost installed. The LogisticRegression
    # hyperparameters below are a byte-for-byte match of make_candidates()'s own
    # "logistic_regression" entry in src/models/bp1_intent_classifier.py - verified by
    # tests/mlops/test_bp1_train_and_register.py comparing the two literal constructions.
    candidates = {"logistic_regression": LogisticRegression(max_iter=1000, random_state=random_state)}
    pipeline = make_pipeline(CHAMPION_NAME, candidates)

    fit_start = time.time()
    pipeline.fit(train_df["text"], y_train)
    fit_seconds = time.time() - fit_start

    y_pred = pipeline.predict(test_df["text"])
    accuracy = float(accuracy_score(y_test, y_pred))
    f1_macro = float(f1_score(y_test, y_pred, average="macro"))
    f1_weighted = float(f1_score(y_test, y_pred, average="weighted"))

    print(f"Real fresh-refit held_out_test_accuracy = {accuracy:.6f} (fit took {fit_seconds:.1f}s)")
    print(f"Real fresh-refit held_out_test_f1_macro  = {f1_macro:.6f}")
    print(
        "Historically recorded (configs/bp1_customer_intent_classification.yaml): "
        "accuracy=0.822403, f1_macro=0.8221"
    )

    provenance = tracking.capture_run_provenance(
        dataset_paths=[args.data_dir / "banking77_train.csv", args.data_dir / "banking77_test.csv"]
    )

    exp_id = tracking.configure_mlflow(EXPERIMENT_NAME, args.mlruns_dir)
    import mlflow

    mlflow.set_tracking_uri(tracking.get_tracking_uri(args.mlruns_dir))
    with mlflow.start_run(
        experiment_id=exp_id, run_name=f"bp1_{CHAMPION_NAME}_refit{args.run_name_suffix}"
    ) as run:
        mlflow.log_params(
            {
                "bp_id": "bp1",
                "champion_model": CHAMPION_NAME,
                "random_state": random_state,
                "n_train_rows": len(train_df),
                "n_test_rows": len(test_df),
                "git_sha": provenance["git_sha"],
                "git_dirty": provenance["git_dirty"],
            }
        )
        mlflow.log_metrics(
            {
                "held_out_test_accuracy": accuracy,
                "held_out_test_f1_macro": f1_macro,
                "held_out_test_f1_weighted": f1_weighted,
                "fit_seconds": fit_seconds,
            }
        )
        for pkg, ver in provenance["software_versions"].items():
            mlflow.set_tag(f"software__{pkg}", ver)
        mlflow.set_tag("dataset_combined_sha256", provenance["dataset_fingerprint"]["combined_sha256"])
        mlflow.set_tag("historical_accuracy_comparison", "0.822403")

        bundle = {
            "bp_id": "bp1",
            "champion_name": CHAMPION_NAME,
            "pipeline": pipeline,
            "label_encoder": label_encoder,
            "class_names": list(label_encoder.classes_),
            "metadata": {
                "held_out_test_accuracy": accuracy,
                "held_out_test_f1_macro": f1_macro,
                "random_state": random_state,
                "git_sha": provenance["git_sha"],
            },
        }
        bundle_path = args.models_dir / "bp1_champion_pipeline.joblib"
        save_stats = save_model_bundle(bundle, bundle_path)
        mlflow.log_artifact(str(bundle_path), artifact_path="model")
        mlflow.set_tag("joblib_sha256", save_stats["sha256"])
        mlflow.set_tag("joblib_size_bytes", str(save_stats["size_bytes"]))

        run_id = run.info.run_id

    print(f"MLflow run_id = {run_id}")
    print(
        f"Real joblib bundle saved to {bundle_path} "
        f"(sha256={save_stats['sha256']}, size={save_stats['size_bytes']} bytes)"
    )

    import os

    os.environ["MLFLOW_TRACKING_URI"] = tracking.get_tracking_uri(args.mlruns_dir)
    version_info = registry.register_model_version(
        bp_id="bp1",
        run_id=run_id,
        artifact_subpath="model/bp1_champion_pipeline.joblib",
        provenance_tags=provenance,
        evaluation_metrics={
            "held_out_test_accuracy": accuracy,
            "held_out_test_f1_macro": f1_macro,
            "held_out_test_f1_weighted": f1_weighted,
        },
        description="BP1 logistic_regression champion, real fresh refit on BANKING77 (Phase D).",
    )
    print(f"Registered: {version_info.name} version {version_info.version} (run_id={version_info.run_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
