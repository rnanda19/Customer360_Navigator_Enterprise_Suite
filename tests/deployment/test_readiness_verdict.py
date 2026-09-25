"""
tests/deployment/test_readiness_verdict.py — Customer360 Navigator

Tests for src/deployment/readiness_verdict.py (Hardening Step 4). Builds a small, complete
SYNTHETIC project tree per test (config YAML, a real fitted+persisted joblib bundle, pyproject.toml,
requirements.txt, and importable dummy service modules) so the module's checks can be exercised
against every real code path - happy path, missing-artifact PENDING states, and tampered/drifted
FAIL states - without touching any real BP1/BP2 data or the real device project. Mirrors this
project's established synthetic-fixture test style (see tests/shared/test_model_persistence.py and
tests/services/test_bp{1,2}_inference_service.py).
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder

from deployment.readiness_verdict import (
    SUPPORTED_BPS,
    CheckStatus,
    _resolve_config_relative_path,
    assess_deployment_readiness,
)
from models.model_persistence import save_model_bundle

FAKE_BP = "bp1"  # reuses the real bp1 wiring (config keys, service module name) against a fake tree


def _build_project_tree(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "configs").mkdir(parents=True)
    (project_root / "models" / "bp1_customer_intent_classification").mkdir(parents=True)
    (project_root / "src" / "services").mkdir(parents=True)
    (project_root / "src" / "models").mkdir(parents=True)
    (project_root / "tests" / "shared").mkdir(parents=True)
    (project_root / "tests" / "services").mkdir(parents=True)
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("locked\n", encoding="utf-8")
    (project_root / "requirements.txt").write_text(
        "joblib>=1.3\nhttpx>=0.27\nfastapi>=0.115\n", encoding="utf-8"
    )
    (project_root / "pyproject.toml").write_text(
        'dependencies = [\n    "fastapi>=0.115",\n    "pydantic>=2.0",\n    "joblib>=1.3",\n]\n',
        encoding="utf-8",
    )
    return project_root


def _fit_and_persist_bp1_bundle(bundle_path):
    texts = ["card lost", "card stolen", "transfer failed", "transfer pending"]
    labels = ["lost_card", "lost_card", "transfer_issue", "transfer_issue"]
    label_encoder = LabelEncoder().fit(labels)
    y = label_encoder.transform(labels)
    pipeline = Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=1000))])
    pipeline.fit(texts, y)
    bundle = {
        "bp_id": "bp1",
        "champion_name": "logistic_regression",
        "pipeline": pipeline,
        "label_encoder": label_encoder,
        "class_names": list(label_encoder.classes_),
        "metadata": {"synthetic_fixture": True},
    }
    stats = save_model_bundle(bundle, bundle_path)
    accuracy = float(pipeline.score(texts, y))
    return stats, accuracy


def _write_working_service_module(project_root):
    """A minimal-but-real FastAPI app with the three required routes - not a mock of the real
    bp1_inference_service.py, but real enough to exercise the import/route-detection checks.
    """
    (project_root / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "src" / "services" / "bp1_inference_service.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "def root(): return {}\n"
        "@app.get('/health')\n"
        "def health(): return {}\n"
        "@app.post('/predict')\n"
        "def predict(): return {}\n",
        encoding="utf-8",
    )


def _write_config(
    project_root,
    *,
    include_persistence_block,
    stats=None,
    accuracy=None,
    gate_accuracy=0.75,
    sha256_override=None,
    reload_diff=0.0,
):
    lines = [
        "gate3_model_benchmark:",
        "  champion_model: logistic_regression",
        f"  held_out_test_accuracy: {gate_accuracy}",
    ]
    if include_persistence_block:
        joblib_relative_path = "models/bp1_customer_intent_classification/bundle.joblib"
        lines += [
            "model_persistence:",
            "  champion_model: logistic_regression",
            f'  joblib_relative_path: "{joblib_relative_path}"',
            f'  joblib_sha256: "{sha256_override or stats["sha256"]}"',
            f"  fresh_refit_test_accuracy: {accuracy if accuracy is not None else gate_accuracy}",
            f"  reload_verified_accuracy: {accuracy if accuracy is not None else gate_accuracy}",
            f"  reload_accuracy_diff: {reload_diff}",
            '  generated_at_utc: "2026-09-22T00:00:00+00:00"',
        ]
    (project_root / "configs" / "bp1_customer_intent_classification.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


@pytest.fixture()
def synthetic_project(tmp_path, monkeypatch):
    project_root = _build_project_tree(tmp_path)
    monkeypatch.syspath_prepend(str(project_root / "src"))
    yield project_root
    for mod in ("services.bp1_inference_service", "services"):
        sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fully_healthy_bp_is_model_artifact_and_service_ready(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=round(accuracy, 6),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "tests" / "shared" / "test_model_persistence.py").write_text("", encoding="utf-8")
    (synthetic_project / "tests" / "services" / "test_bp1_inference_service.py").write_text(
        "", encoding="utf-8"
    )

    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)

    assert verdict.model_artifact_ready is True
    assert verdict.service_ready is True
    assert verdict.fully_deployable is False  # Docker/CI (Steps 5/6) correctly not yet present
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["joblib_bundle_integrity_sha256"] == CheckStatus.PASS.value
    assert statuses["dockerfile_present"] == CheckStatus.PENDING.value
    assert statuses["ci_workflow_present"] == CheckStatus.PENDING.value


# ---------------------------------------------------------------------------
# Honest PENDING states (nothing fabricated when a step hasn't run yet)
# ---------------------------------------------------------------------------


def test_no_config_at_all_reports_fail_not_a_crash(synthetic_project):
    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    assert verdict.model_artifact_ready is False
    assert verdict.service_ready is False
    assert verdict.checks[0].name == "bp_config_exists"
    assert verdict.checks[0].status == CheckStatus.FAIL.value


def test_config_exists_but_no_persistence_block_is_pending_not_fail(synthetic_project):
    """Step 2 (model persistence) simply hasn't been run for real yet - this must read as
    PENDING, the honest current state, never a fabricated PASS or an alarming FAIL."""
    _write_config(synthetic_project, include_persistence_block=False)
    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    assert verdict.model_artifact_ready is False
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["model_persistence_config_block"] == CheckStatus.PENDING.value


# ---------------------------------------------------------------------------
# Real drift/tamper detection - FAIL, never silently accepted
# ---------------------------------------------------------------------------


def test_tampered_bundle_fails_integrity_check(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=round(accuracy, 6),
    )
    # Tamper: append a byte to the real persisted file after the config recorded its real hash.
    with open(bundle_path, "ab") as f:
        f.write(b"\x00")

    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["joblib_bundle_integrity_sha256"] == CheckStatus.FAIL.value
    assert verdict.model_artifact_ready is False


def test_accuracy_drift_between_gate_and_persistence_fails(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    # Gate recorded 0.99 but the persistence notebook's own fresh refit got the real ~1.0 (trivial
    # synthetic data) - force a real, detectable mismatch beyond tolerance.
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=0.10,
    )
    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["accuracy_consistent_with_gate_record"] == CheckStatus.FAIL.value
    assert verdict.model_artifact_ready is False


def test_missing_bundle_file_fails_not_pending(synthetic_project):
    """Config claims a bundle was persisted, but the file isn't there - config/disk have
    drifted (deleted after the notebook ran, or a bad manual edit). This is a real FAIL, distinct
    from the honest PENDING case where the notebook simply never ran."""
    fake_stats = {"sha256": "0" * 64}
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=fake_stats,
        accuracy=0.9,
    )
    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["joblib_bundle_exists_on_disk"] == CheckStatus.FAIL.value
    assert verdict.model_artifact_ready is False


def test_broken_service_module_fails_import_check(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=round(accuracy, 6),
    )
    (synthetic_project / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (synthetic_project / "src" / "services" / "bp1_inference_service.py").write_text(
        "raise RuntimeError('deliberately broken for this test')\n", encoding="utf-8"
    )

    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["service_module_imports_cleanly"] == CheckStatus.FAIL.value
    assert verdict.service_ready is False


def test_missing_httpx_dependency_declaration_fails(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=round(accuracy, 6),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "requirements.txt").write_text("joblib>=1.3\n", encoding="utf-8")  # httpx removed

    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["requirements_declares_httpx"] == CheckStatus.FAIL.value
    assert verdict.service_ready is False


# ---------------------------------------------------------------------------
# Real subprocess test-suite execution (not mocked)
# ---------------------------------------------------------------------------


def test_run_tests_true_actually_executes_pytest_subprocess(synthetic_project):
    bundle_path = synthetic_project / "models" / "bp1_customer_intent_classification" / "bundle.joblib"
    stats, accuracy = _fit_and_persist_bp1_bundle(bundle_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        stats=stats,
        accuracy=round(accuracy, 6),
        gate_accuracy=round(accuracy, 6),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "tests" / "shared" / "test_model_persistence.py").write_text(
        "def test_trivial_pass():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    (synthetic_project / "tests" / "services" / "test_bp1_inference_service.py").write_text(
        "def test_trivial_fail():\n    assert False, 'deliberate failure for this test'\n",
        encoding="utf-8",
    )

    verdict = assess_deployment_readiness(FAKE_BP, synthetic_project, run_tests=True)
    statuses = {c.name: (c.status, c.detail) for c in verdict.checks}
    status, detail = statuses["test_suite_passes"]
    assert status == CheckStatus.FAIL.value  # the deliberate failure above must be caught, not hidden
    assert "pytest exited" in detail
    assert verdict.service_ready is False


# ---------------------------------------------------------------------------
# BP3-specific fixtures - prove the Step 4 metric-name generalization actually works for a
# non-accuracy metric (BP3's real fidelity metric is PR-AUC, never accuracy). Deliberately a
# separate, explicit builder (not a parametrized generalization of the bp1 one above) - matching
# this project's established per-BP-explicit test style rather than introducing new indirection.
# ---------------------------------------------------------------------------


def _build_bp3_project_tree(tmp_path):
    project_root = tmp_path / "project_bp3"
    (project_root / "configs").mkdir(parents=True)
    (project_root / "models" / "bp3_complaint_escalation_prediction").mkdir(parents=True)
    (project_root / "src" / "services").mkdir(parents=True)
    (project_root / "src" / "models").mkdir(parents=True)
    (project_root / "tests" / "shared").mkdir(parents=True)
    (project_root / "tests" / "services").mkdir(parents=True)
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("locked\n", encoding="utf-8")
    (project_root / "requirements.txt").write_text(
        "joblib>=1.3\nhttpx>=0.27\nfastapi>=0.115\n", encoding="utf-8"
    )
    (project_root / "pyproject.toml").write_text(
        'dependencies = [\n    "fastapi>=0.115",\n    "pydantic>=2.0",\n    "joblib>=1.3",\n]\n',
        encoding="utf-8",
    )
    return project_root


def _fit_and_persist_bp3_bundle(bundle_path):
    """BP3-shaped dict bundle - OneHotEncoder ColumnTransformer + company-frequency hstack, a
    binary classifier, and deliberately NO label_encoder key (BP3's real target is already 0/1 -
    see model_persistence.py's module docstring). Mirrors tests/shared/test_model_persistence.py's
    own bp3_bundle fixture."""
    products = ["credit_card", "credit_card", "mortgage", "mortgage"]
    companies = ["Acme Bank", "Beta Bank", "Acme Bank", "Beta Bank"]
    y = np.array([0, 1, 0, 1])
    X_raw = pd.DataFrame({"Product": products, "Company": companies})

    company_freq_map = X_raw["Company"].value_counts(normalize=True).to_dict()
    company_freq_col = X_raw["Company"].map(company_freq_map).to_numpy().reshape(-1, 1)

    preprocessor = ColumnTransformer(
        transformers=[("cat", OneHotEncoder(handle_unknown="ignore"), ["Product"])],
        remainder="drop",
    )
    X_ohe = preprocessor.fit_transform(X_raw[["Product"]])
    X_ohe_dense = X_ohe.toarray() if hasattr(X_ohe, "toarray") else np.asarray(X_ohe)
    X_full = np.hstack([X_ohe_dense, company_freq_col])

    classifier = LogisticRegression(max_iter=1000).fit(X_full, y)
    bundle = {
        "bp_id": "bp3",
        "champion_name": "xgboost",
        "preprocessor": preprocessor,
        "company_freq_map": company_freq_map,
        "feature_cols_categorical": ["Product"],
        "company_col": "Company",
        "classifier": classifier,
        "class_names": ["0", "1"],
        "needs_dense": True,
        "metadata": {"synthetic_fixture": True},
    }
    stats = save_model_bundle(bundle, bundle_path)
    proba = classifier.predict_proba(X_full)[:, 1]
    pr_auc = float(average_precision_score(y, proba))
    return stats, pr_auc


def _write_bp3_config(
    project_root,
    *,
    include_persistence_block,
    stats=None,
    pr_auc=None,
    gate_pr_auc=0.35,
    sha256_override=None,
    reload_diff=0.0,
):
    lines = [
        "gate5_decision_layer:",
        "  champion_model: xgboost",
        f"  held_out_test_pr_auc_recomputed: {gate_pr_auc}",
    ]
    if include_persistence_block:
        joblib_relative_path = "models/bp3_complaint_escalation_prediction/bundle.joblib"
        lines += [
            "model_persistence:",
            "  champion_model: xgboost",
            f'  joblib_relative_path: "{joblib_relative_path}"',
            f'  joblib_sha256: "{sha256_override or stats["sha256"]}"',
            f"  fresh_refit_test_pr_auc: {pr_auc if pr_auc is not None else gate_pr_auc}",
            f"  reload_pr_auc_diff: {reload_diff}",
            '  generated_at_utc: "2026-09-24T00:00:00+00:00"',
        ]
    (project_root / "configs" / "bp3_complaint_escalation_prediction.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_working_bp3_service_module(project_root):
    (project_root / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "src" / "services" / "bp3_inference_service.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "def root(): return {}\n"
        "@app.get('/health')\n"
        "def health(): return {}\n"
        "@app.post('/predict')\n"
        "def predict(): return {}\n",
        encoding="utf-8",
    )


@pytest.fixture()
def synthetic_bp3_project(tmp_path, monkeypatch):
    project_root = _build_bp3_project_tree(tmp_path)
    monkeypatch.syspath_prepend(str(project_root / "src"))
    yield project_root
    for mod in ("services.bp3_inference_service", "services"):
        sys.modules.pop(mod, None)


def test_bp3_fully_healthy_uses_pr_auc_metric_fields_not_accuracy(synthetic_bp3_project):
    """Proves the Step 4 generalization actually works for a non-accuracy metric: BP3's real
    persisted fields are fresh_refit_test_pr_auc / reload_pr_auc_diff, compared against
    gate5_decision_layer.held_out_test_pr_auc_recomputed - never accuracy-named fields."""
    bundle_path = (
        synthetic_bp3_project / "models" / "bp3_complaint_escalation_prediction" / "bundle.joblib"
    )
    stats, pr_auc = _fit_and_persist_bp3_bundle(bundle_path)
    _write_bp3_config(
        synthetic_bp3_project,
        include_persistence_block=True,
        stats=stats,
        pr_auc=round(pr_auc, 6),
        gate_pr_auc=round(pr_auc, 6),
    )
    _write_working_bp3_service_module(synthetic_bp3_project)
    (synthetic_bp3_project / "tests" / "shared" / "test_model_persistence.py").write_text(
        "", encoding="utf-8"
    )
    (synthetic_bp3_project / "tests" / "services" / "test_bp3_inference_service.py").write_text(
        "", encoding="utf-8"
    )

    verdict = assess_deployment_readiness("bp3", synthetic_bp3_project, run_tests=False)

    assert verdict.model_artifact_ready is True
    assert verdict.service_ready is True
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["joblib_bundle_integrity_sha256"] == CheckStatus.PASS.value
    assert statuses["accuracy_consistent_with_gate_record"] == CheckStatus.PASS.value
    assert statuses["reload_fidelity_verified_at_run_time"] == CheckStatus.PASS.value


def test_bp3_pr_auc_drift_between_gate_and_persistence_fails(synthetic_bp3_project):
    bundle_path = (
        synthetic_bp3_project / "models" / "bp3_complaint_escalation_prediction" / "bundle.joblib"
    )
    stats, pr_auc = _fit_and_persist_bp3_bundle(bundle_path)
    # Gate recorded a real PR-AUC well outside tolerance of the persistence notebook's own fresh
    # refit - a real, detectable metric-drift FAIL, exercised on BP3's PR-AUC field names rather
    # than bp1's accuracy-named ones, proving the generalization isn't just accuracy in disguise.
    _write_bp3_config(
        synthetic_bp3_project,
        include_persistence_block=True,
        stats=stats,
        pr_auc=round(pr_auc, 6),
        gate_pr_auc=0.05,
    )
    verdict = assess_deployment_readiness("bp3", synthetic_bp3_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["accuracy_consistent_with_gate_record"] == CheckStatus.FAIL.value
    assert verdict.model_artifact_ready is False


# ---------------------------------------------------------------------------
# _resolve_config_relative_path - cross-platform joblib_relative_path handling. A real bug found
# 2026-09-24 while verifying BP3's Docker packaging (Hardening Step 5) against BP3's real,
# already-real-run config: the persistence notebooks wrote joblib_relative_path into a
# DOUBLE-QUOTED YAML scalar via a raw Windows path (backslash-separated), and YAML's own escape
# processing silently corrupted it (`\b` -> a literal backspace control character, since both real
# path segments happened to start with "b") - not merely a separator-style mismatch, but actual
# data loss at YAML-parse time. Confirmed directly against BP3's real on-disk config value, not
# assumed. The notebooks now write `.as_posix()` so this cannot recur in a freshly-written config;
# these tests cover both the already-corrupted case (must still resolve correctly, no rerun
# required) and the now-standard clean forward-slash case.
# ---------------------------------------------------------------------------


def test_resolve_config_relative_path_handles_clean_forward_slash_path(tmp_path):
    target = tmp_path / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    resolved = _resolve_config_relative_path(
        tmp_path, "models/bp3_complaint_escalation_prediction/bp3_champion_bundle.joblib"
    )
    assert resolved == target
    assert resolved.exists()


def test_resolve_config_relative_path_handles_literal_windows_backslashes(tmp_path):
    """Covers the case where the raw config string still has literal backslash characters (e.g. a
    single-quoted YAML scalar, where YAML never treats backslash as an escape) - portable splitting
    alone (no reversal needed) must still resolve it correctly on this Linux test runner."""
    target = tmp_path / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    resolved = _resolve_config_relative_path(
        tmp_path, "models\\bp3_complaint_escalation_prediction\\bp3_champion_bundle.joblib"
    )
    assert resolved == target
    assert resolved.exists()


def test_resolve_config_relative_path_reverses_real_yaml_escape_corruption(tmp_path):
    """Reproduces the exact real corruption found in BP3's own on-disk config: a double-quoted YAML
    scalar containing `\\b` (backslash + the letter b) gets parsed by yaml.safe_load into a single
    backspace control character (0x08), not two literal characters - this is what
    _resolve_config_relative_path actually receives as input in the real failing case, not a
    literal backslash."""
    target = tmp_path / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    # The real corrupted value yaml.safe_load produces from the config line
    # `joblib_relative_path: "models\bp3_complaint_escalation_prediction\bp3_champion_bundle.joblib"`
    yaml_corrupted_value = yaml.safe_load(
        '"models\\bp3_complaint_escalation_prediction\\bp3_champion_bundle.joblib"'
    )
    assert "\x08" in yaml_corrupted_value  # sanity: reproduces the real corruption, not a no-op string
    resolved = _resolve_config_relative_path(tmp_path, yaml_corrupted_value)
    assert resolved == target
    assert resolved.exists()


def test_bp3_readiness_check_resolves_real_corrupted_joblib_path(synthetic_bp3_project):
    """End-to-end: a full assess_deployment_readiness() pass against a config file written the
    exact real (buggy, pre-fix) way - a raw Windows-style backslash path embedded directly in a
    double-quoted YAML scalar - must still find the bundle. The ON-DISK text below is the literal
    two characters backslash+"b" (matching what the old notebook f-string actually wrote to disk);
    it is yaml.safe_load() itself, inside assess_deployment_readiness(), that turns those into the
    single corrupted control character at parse time - reproducing the real failure path end to
    end, not just the helper function in isolation."""
    bundle_path = (
        synthetic_bp3_project
        / "models"
        / "bp3_complaint_escalation_prediction"
        / "bp3_champion_bundle.joblib"
    )
    stats, pr_auc = _fit_and_persist_bp3_bundle(bundle_path)
    raw_windows_style_path = "models\\bp3_complaint_escalation_prediction\\bp3_champion_bundle.joblib"
    lines = [
        "gate5_decision_layer:",
        "  champion_model: xgboost",
        f"  held_out_test_pr_auc_recomputed: {round(pr_auc, 6)}",
        "model_persistence:",
        "  champion_model: xgboost",
        f'  joblib_relative_path: "{raw_windows_style_path}"',
        f'  joblib_sha256: "{stats["sha256"]}"',
        f"  fresh_refit_test_pr_auc: {round(pr_auc, 6)}",
        "  reload_pr_auc_diff: 0.0",
        '  generated_at_utc: "2026-09-24T00:00:00+00:00"',
    ]
    (synthetic_bp3_project / "configs" / "bp3_complaint_escalation_prediction.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    verdict = assess_deployment_readiness("bp3", synthetic_bp3_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["joblib_bundle_exists_on_disk"] == CheckStatus.PASS.value
    assert statuses["joblib_bundle_integrity_sha256"] == CheckStatus.PASS.value


def test_supported_bps_registry_covers_bp1_bp2_and_bp3():
    assert set(SUPPORTED_BPS) == {"bp1", "bp2", "bp3"}
    for bp_id, bp_config in SUPPORTED_BPS.items():
        for required_field in (
            "champion_config_block",
            "champion_metric_key",
            "persistence_metric_key",
            "persistence_reload_diff_key",
            "metric_label",
        ):
            assert required_field in bp_config, f"{bp_id} registry entry missing {required_field!r}"


def test_unsupported_bp_id_raises():
    with pytest.raises(ValueError):
        assess_deployment_readiness("bp99")
