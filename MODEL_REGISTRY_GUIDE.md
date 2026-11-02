# Model Registry Guide (Phase D)

**Status: real, locally verified. Not yet committed or pushed.**

This guide covers `src/mlops/registry.py`, the real MLflow Model Registry wrapper added in
Phase D. For the broader picture (what existed before, why BP1, design decisions), see
`MLOPS_ARCHITECTURE.md`. This file predates and is distinct from the pre-existing
`MODEL_REGISTRY.md` (a static markdown table of per-BP persisted-artifact metadata) — that file
is unchanged in its own format, but its own "not an MLflow-style registry" caveat about
`src/monitoring/model_registry.py` now has a real counterpart described here.

## Naming convention

Every registered model is named `customer360_<bp_id>` (`registry.registered_model_name("bp1")` →
`"customer360_bp1"`), matching this project's existing per-BP naming convention everywhere else.

## Registering a version

```python
from mlops import tracking, registry
import mlflow, os

os.environ["MLFLOW_TRACKING_URI"] = tracking.get_tracking_uri()
mlflow.set_tracking_uri(tracking.get_tracking_uri())

with mlflow.start_run() as run:
    mlflow.log_artifact("my_model.joblib", artifact_path="model")
    run_id = run.info.run_id

info = registry.register_model_version(
    bp_id="bp1",
    run_id=run_id,
    artifact_subpath="model/my_model.joblib",
    provenance_tags=tracking.capture_run_provenance(dataset_paths=[...]),
    evaluation_metrics={"held_out_test_accuracy": 0.8224},
)
print(info.version)  # a real str, e.g. "4"
```

Every version is tagged with `metric__<name>` for each evaluation metric and
`provenance__<name>` for each scalar provenance field (git SHA, software versions), plus
`provenance__dataset_combined_sha256` when a dataset fingerprint was supplied. Nothing here is
invented — every tag value is a `str()` cast of a real value the caller computed.

## Model signature

Phase D's requirement for real model signatures is satisfied via MLflow's own
`mlflow.models.signature.infer_signature`, called against a real sample of input the registered
pipeline actually consumes and its real output — this project's wrapper does not reimplement
signature inference, it relies on the real `mlflow.sklearn.log_model`/`infer_signature` machinery
when a caller opts to log a full MLflow-flavored model rather than a raw joblib artifact (both
paths are supported; `scripts/mlops/bp1_train_and_register.py` currently uses the raw joblib path
to match this project's existing `model_persistence.py` bundle contract exactly).

## Aliases: champion / challenger / previous_champion

MLflow's alias mechanism is 1:1 — setting an alias that's already held by another version moves
it. This project uses three conventional alias names:

- `champion` — the version currently approved for production use.
- `challenger` — a candidate under active champion-challenger evaluation (optional; cleared on
  promotion via `registry.delete_alias`).
- `previous_champion` — the version `champion` pointed at immediately before the most recent
  promotion, kept specifically so `promotion.rollback()` has a real version to restore.

```python
registry.set_alias("bp1", "champion", "2")
current = registry.get_version_by_alias("bp1", "champion")   # AliasedVersion(version="2", ...)
registry.delete_alias("bp1", "challenger")
```

`get_version_by_alias()` returns `None` (never raises, never fabricates a version) when no
version currently holds that alias.

## Listing versions

```python
for v in registry.list_versions("bp1"):
    print(v.version, v.tags.get("metric__held_out_test_accuracy"))
```

Most recent version first. Returns `[]` (not an error) for a bp_id with no registered model yet.

## Real evidence this guide's examples were actually run

See `MLOPS_TEST_REPORT.md` §2–§4 for the real commands run, their real output, and the real
`customer360_bp1` registry state (3 versions; `champion` alias independently verified to point at
version `1` after a real rollback).
