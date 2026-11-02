"""
scripts/mlops/ci_demo.py — Customer360 Navigator

PHASE D CI gate (.github/workflows/mlops-verify.yml): a real, standalone, synthetic-data
end-to-end demonstration of registry registration, governance pass/fail, promotion, and
rollback, runnable on any CI runner with no external data (the real BANKING77-backed
demonstration lives in scripts/mlops/bp1_train_and_register.py and was run and verified locally -
see MLOPS_TEST_REPORT.md - because CI has no access to the real, intentionally-gitignored
BANKING77 CSVs). This script asserts its own real expectations and exits non-zero on any
failure, so CI fails loudly if registry/governance/promotion/rollback mechanics regress.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    tmp_mlruns = tempfile.mkdtemp(prefix="ci_mlops_demo_")
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{tmp_mlruns}/mlflow.db"

    import joblib
    import mlflow
    from sklearn.linear_model import LogisticRegression

    from mlops import champion_challenger, governance, promotion, registry

    mlflow.set_experiment("ci_demo")
    model_path = Path(tmp_mlruns) / "ci_demo_model.joblib"
    with mlflow.start_run() as run:
        clf = LogisticRegression().fit([[0], [1], [2], [3]], [0, 0, 1, 1])
        joblib.dump(clf, model_path)
        mlflow.log_artifact(str(model_path), artifact_path="model")
        run_id = run.info.run_id

    good = registry.register_model_version(
        bp_id="ci_demo",
        run_id=run_id,
        artifact_subpath=f"model/{model_path.name}",
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.90},
    )
    thresholds = {"ci_demo": {"accuracy": 0.80}}
    doc = {"champion_model": "x", "trained_on": "y", "evaluated_on": "z", "intended_use": "w"}

    gov_good = governance.validate_candidate("ci_demo", {"accuracy": 0.90}, doc, thresholds=thresholds)
    assert gov_good.passed, "CI DEMO FAILED: a 0.90-accuracy candidate should pass governance"
    verdict_good = champion_challenger.evaluate_challenger(
        "ci_demo", "accuracy", {"accuracy": 0.90}, {"accuracy": 0.90}
    )
    approval = promotion.require_explicit_approval(
        approved=True, actor="github-actions-ci", reason="CI demonstration promotion"
    )
    promotion.promote_candidate(
        "ci_demo",
        good.version,
        governance_result=gov_good,
        challenger_verdict=verdict_good,
        approval=approval,
    )
    champ = registry.get_version_by_alias("ci_demo", "champion")
    assert (
        champ is not None and champ.version == good.version
    ), "CI DEMO FAILED: promotion did not set champion alias"
    print(f"PASS: promoted version {champ.version} to champion.")

    gov_bad = governance.validate_candidate("ci_demo", {"accuracy": 0.10}, doc, thresholds=thresholds)
    assert not gov_bad.passed, "CI DEMO FAILED: a 0.10-accuracy candidate should FAIL governance"
    print(f"PASS: weak candidate correctly rejected by governance: {gov_bad.reasons}")

    promotion.rollback(
        "ci_demo", actor="github-actions-ci", reason="CI demonstration rollback", target_version=good.version
    )
    champ_after = registry.get_version_by_alias("ci_demo", "champion")
    assert (
        champ_after.version == good.version
    ), "CI DEMO FAILED: rollback did not restore the expected version"
    print(f"PASS: rollback independently verified - champion alias == {champ_after.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
