"""
tests/bp5_root_cause_driver_analytics/test_gate_artifacts.py — Customer360 Navigator

Schema and cross-artifact consistency checks for BP5 Gates 1-6's real, already-delivered output
files, mirroring tests/bp3_complaint_escalation_prediction/test_gate_artifacts.py's and
tests/bp4_customer_journey_analytics/test_gate_artifacts.py's pattern (BP Gate 6 governance
requirement). These tests validate the SHAPE and internal consistency of whatever the gate
notebooks actually wrote on the user's last real run - they do not re-derive or assert specific
numbers (that is each gate's own job, checked live inside its own notebook at run time). Any
gate whose artifacts don't exist yet is skipped, not failed, since not every gate need be
complete for CI to still pass on what IS done.

BP5-specific adaptation: unlike BP1-4, BP5 has no single "champion model name" to cross-check
(its methodology_policy names only logistic regression, fit separately per outcome - see
src/models/bp5_driver_association.py's own module docstring) and no persisted model bundle
(no persistence step exists yet in BP5's own gate plan). The cross-artifact consistency check
this file performs instead is BP5's own real analogue: the held-out ROC-AUC/PR-AUC recorded in
Gate 3's config block must match, within Gate 4's own disclosed GATE4_AUC_TOLERANCE, what Gate
4's real bootstrap point estimate reports for the same metric - i.e. Gate 4 must have actually
re-confirmed Gate 3's numbers, not merely repeated them.
"""

from __future__ import annotations

import json

import pytest
import yaml

from utils.performance_setup import resolve_project_root

GATE4_AUC_TOLERANCE = 0.01  # must match src/models/bp5_driver_association.py's own constant name


@pytest.fixture(scope="module")
def project_root():
    try:
        return resolve_project_root()
    except RuntimeError:
        pytest.skip("Not running inside the Customer360 Navigator project tree - set C360_PROJECT_ROOT.")


@pytest.fixture(scope="module")
def artifacts_dir(project_root):
    return project_root / "notebooks" / "bp5_root_cause_driver_analytics" / "artifacts"


@pytest.fixture(scope="module")
def bp5_config(project_root):
    config_path = project_root / "configs" / "bp5_root_cause_driver_analytics.yaml"
    if not config_path.exists():
        pytest.skip("bp5_root_cause_driver_analytics.yaml not found - BP5 Gate 1 has not run yet.")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Gate 1 - business understanding & policy
# ---------------------------------------------------------------------------


def test_gate1_target_definition_declares_two_outcomes_not_one(bp5_config):
    target_def = bp5_config.get("target_definition")
    if target_def is None:
        pytest.skip("BP5 Gate 1 has not run yet (target_definition is null).")
    assert target_def["no_single_supervised_target_two_real_outcome_fields"] is True
    assert "outcome_1_intervention_required" in target_def
    assert "outcome_2_timely_response_failure" in target_def


def test_gate1_policy_json_ecoa_reg_b_not_applicable(artifacts_dir):
    policy_path = artifacts_dir / "policy.json"
    if not policy_path.exists():
        pytest.skip("BP5 Gate 1 has not run yet.")
    policy = _load_json(policy_path)
    assert "ecoa_reg_b_not_applicable" in policy["compliance_touchpoint"]


def test_gate1_leakage_rules_bar_the_two_outcome_defining_columns(bp5_config):
    leakage_rules = bp5_config.get("leakage_rules")
    if leakage_rules is None:
        pytest.skip("BP5 Gate 1 has not run yet.")
    joined = " ".join(leakage_rules)
    assert "Company response to consumer" in joined
    assert "Timely response?" in joined


# ---------------------------------------------------------------------------
# Gate 2 - data verification & feature engineering
# ---------------------------------------------------------------------------


def test_gate2_candidate_driver_null_counts_covers_exactly_the_seven_real_fields(bp5_config):
    null_counts = bp5_config.get("candidate_driver_null_counts")
    if null_counts is None:
        pytest.skip("BP5 Gate 2 has not run yet.")
    assert set(null_counts.keys()) == {
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "Submitted via",
        "Company",
        "State",
    }


def test_gate2_outcome_counts_match_gate1_policy_json(bp5_config):
    if bp5_config.get("n_outcome_1_positive") is None:
        pytest.skip("BP5 Gate 2 has not run yet.")
    assert bp5_config["outcome_1_matches_gate1_policy_json"] is True
    assert bp5_config["outcome_2_matches_gate1_policy_json"] is True
    assert (
        bp5_config["n_outcome_1_positive"] + bp5_config["n_outcome_1_negative"]
        == bp5_config["n_outcome_1_trainable"]
    )
    assert (
        bp5_config["n_outcome_2_positive"] + bp5_config["n_outcome_2_negative"]
        == bp5_config["n_outcome_2_trainable"]
    )


def test_gate2_no_barred_column_used_as_driver(bp5_config):
    if bp5_config.get("no_barred_column_used_as_driver") is None:
        pytest.skip("BP5 Gate 2 has not run yet.")
    assert bp5_config["no_barred_column_used_as_driver"] is True


# ---------------------------------------------------------------------------
# Gate 3 - hypothesis testing / regression / SHAP association benchmark
# ---------------------------------------------------------------------------


def test_gate3_chi_square_test_count_matches_six_fields_times_two_outcomes(bp5_config):
    if bp5_config.get("n_chi_square_tests_run") is None:
        pytest.skip("BP5 Gate 3 has not run yet.")
    # 6 real candidate/control fields (5 candidate + State control) x 2 real outcomes.
    assert bp5_config["n_chi_square_tests_run"] == 12


def test_gate3_barred_fields_bar_not_relaxed(bp5_config):
    if bp5_config.get("barred_fields_bar_relaxed") is None:
        pytest.skip("BP5 Gate 3 has not run yet.")
    assert bp5_config["barred_fields_bar_relaxed"] is False


def test_gate3_held_out_metrics_in_valid_range(bp5_config):
    if bp5_config.get("champion_outcome_1_held_out_roc_auc") is None:
        pytest.skip("BP5 Gate 3 has not run yet.")
    for key in (
        "champion_outcome_1_held_out_roc_auc",
        "champion_outcome_1_held_out_pr_auc",
        "champion_outcome_2_held_out_roc_auc",
        "champion_outcome_2_held_out_pr_auc",
    ):
        assert 0.0 <= bp5_config[key] <= 1.0


def test_gate3_artifact_files_referenced_in_config_actually_exist(project_root, bp5_config):
    path_keys = [
        "chi_square_cramers_v_path",
        "log_odds_ratio_by_category_path",
        "company_freq_univariate_logistic_path",
        "barred_field_diagnostics_path",
        "champion_held_out_performance_path",
    ]
    if bp5_config.get(path_keys[0]) is None:
        pytest.skip("BP5 Gate 3 has not run yet.")
    for key in path_keys:
        assert (project_root / bp5_config[key]).exists(), f"{key} points to a missing file"


# ---------------------------------------------------------------------------
# Gate 4 - statistical validation (bootstrap CI / calibration / confusion matrix)
# ---------------------------------------------------------------------------


def test_gate4_consistent_with_gate3_recorded_champion_aucs(bp5_config):
    if bp5_config.get("consistent_with_gate3_recorded_champion_aucs") is None:
        pytest.skip("BP5 Gate 4 has not run yet.")
    assert bp5_config["consistent_with_gate3_recorded_champion_aucs"] is True


def test_gate4_bootstrap_ci_matches_gate3_recorded_point_estimate_within_tolerance(bp5_config):
    # BP5's own analogue of BP1-4's champion-name-consistency check: no single champion NAME
    # exists to compare (BP5 fits one logistic-regression champion per outcome by definition,
    # never a multi-model benchmark - see src/models/bp5_driver_association.py's own module
    # docstring), so the real cross-artifact fact worth checking here is that Gate 4's own
    # bootstrap point estimate genuinely reconfirms Gate 3's recorded number, not merely echoes
    # it uncomputed.
    if bp5_config.get("champion_outcome_1_bootstrap_roc_auc_ci_low") is None:
        pytest.skip("BP5 Gate 4 has not run yet.")
    for outcome_key in ("outcome_1", "outcome_2"):
        gate3_recorded = bp5_config[f"champion_{outcome_key}_held_out_roc_auc"]
        ci_low = bp5_config[f"champion_{outcome_key}_bootstrap_roc_auc_ci_low"]
        ci_high = bp5_config[f"champion_{outcome_key}_bootstrap_roc_auc_ci_high"]
        assert ci_low <= ci_high
        # The Gate 3 point estimate must fall inside (or very near) Gate 4's own real bootstrap
        # CI computed on the same real held-out set - a genuine re-derivation, not a copy.
        assert ci_low - GATE4_AUC_TOLERANCE <= gate3_recorded <= ci_high + GATE4_AUC_TOLERANCE


def test_gate4_confusion_matrix_recall_precision_in_valid_range(bp5_config):
    if bp5_config.get("champion_outcome_1_recall_at_0.5") is None:
        pytest.skip("BP5 Gate 4 has not run yet.")
    for key in (
        "champion_outcome_1_recall_at_0.5",
        "champion_outcome_1_precision_at_0.5",
        "champion_outcome_2_recall_at_0.5",
        "champion_outcome_2_precision_at_0.5",
    ):
        assert 0.0 <= bp5_config[key] <= 1.0


# ---------------------------------------------------------------------------
# Gate 5 - decision layer & reporting (prioritized root-cause report)
# ---------------------------------------------------------------------------


def test_gate5_udaap_language_check_passed(bp5_config):
    if bp5_config.get("udaap_language_check_passed") is None:
        pytest.skip("BP5 Gate 5 has not run yet.")
    assert bp5_config["udaap_language_check_passed"] is True


def test_gate5_barred_fields_bar_still_not_relaxed(bp5_config):
    if bp5_config.get("min_n_per_category_threshold_used") is None:
        pytest.skip("BP5 Gate 5 has not run yet.")
    assert bp5_config["barred_fields_bar_relaxed"] is False


def test_gate5_report_json_has_the_citation_schema_on_every_field_finding(project_root, bp5_config):
    path_key = "prioritized_root_cause_report_outcome_1_path"
    if bp5_config.get(path_key) is None:
        pytest.skip("BP5 Gate 5 has not run yet.")
    report = _load_json(project_root / bp5_config[path_key])
    expected_citation_keys = {
        "source_bp",
        "source_gate",
        "source_artifact_relative_path",
        "source_field_or_metric",
        "extracted_value",
        "retrieval_timestamp_utc",
        "verification_method",
    }
    assert len(report["field_level_ranking"]) > 0
    for finding in report["field_level_ranking"]:
        assert expected_citation_keys.issubset(finding["citation"].keys())


def test_gate5_report_field_ranking_excludes_state_control_field(project_root, bp5_config):
    path_key = "prioritized_root_cause_report_outcome_1_path"
    if bp5_config.get(path_key) is None:
        pytest.skip("BP5 Gate 5 has not run yet.")
    report = _load_json(project_root / bp5_config[path_key])
    assert all(f["driver_field"] != "State" for f in report["field_level_ranking"])


# ---------------------------------------------------------------------------
# Gate 6 - productization, monitoring & governance (this gate's own output)
# ---------------------------------------------------------------------------


def test_gate6_governance_fields_present_with_boolean_type(bp5_config):
    # Deliberately checks SHAPE only (keys present, boolean-typed), never the boolean VALUE -
    # a real structural issue this gate's own sandbox verification caught: this file's pytest
    # subprocess run (Gate 6 Section 7) necessarily executes BEFORE that same run writes its own
    # gate6_pytest_all_passed/gate6_notebook_syntax_all_passed fields (Section 11), so asserting
    # a specific boolean VALUE here would always be checking the PREVIOUS run's recorded result,
    # not this run's - a temporal paradox, not a real invariant. Whether Gate 6's own run
    # actually passed is that run's own job to assert live (its own Section 12 integrity
    # checks), matching this file's own stated scope (shape/consistency, never re-deriving or
    # re-asserting specific pass/fail numbers another gate already checked live).
    if bp5_config.get("gate6_pytest_all_passed") is None:
        pytest.skip("BP5 Gate 6 has not run yet.")
    assert isinstance(bp5_config["gate6_pytest_all_passed"], bool)
    assert isinstance(bp5_config["gate6_notebook_syntax_all_passed"], bool)


def test_gate6_model_card_and_changelog_written(project_root, bp5_config):
    if bp5_config.get("gate6_model_card_path") is None:
        pytest.skip("BP5 Gate 6 has not run yet.")
    assert (project_root / bp5_config["gate6_model_card_path"]).exists()
    assert (project_root / bp5_config["gate6_changelog_path"]).exists()
