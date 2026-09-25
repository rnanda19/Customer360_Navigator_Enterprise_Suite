"""
tests/bp7_customer_navigator_decision_engine/test_gate_artifacts.py — Customer360 Navigator

Schema / cross-artifact consistency checks over BP7's real, currently saved Gates 1-6 artifacts -
matching BP5's and BP6's own test_gate_artifacts.py precedent. Every test is SKIPPED (never failed)
when the real artifact it needs has not been produced yet by a real run - this file makes no
network call (BP7 makes none anywhere) and never generates, mocks, or fabricates a substitute
artifact; it only inspects what is really on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore")

KNOWN_RECOMMENDED_ACTIONS = {
    "UNSCORED_MISSING_UPSTREAM_INPUT",
    "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
    "ESCALATE_SENIOR_REVIEWER",
    "PRIORITY_QUEUE_REVIEW",
    "STANDARD_QUEUE",
}


@pytest.fixture(scope="module")
def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return candidate
    pytest.skip("Not running inside the Customer360 Navigator project tree.")


@pytest.fixture(scope="module")
def artifacts_dir(project_root: Path) -> Path:
    return project_root / "notebooks" / "bp7_customer_navigator_decision_engine" / "artifacts"


def _load_or_skip(path: Path, what: str) -> dict:
    if not path.exists():
        pytest.skip(f"{what} has not been run for real yet ({path} does not exist).")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------------------------
# Gate 1 policy
# --------------------------------------------------------------------------------------------


def test_gate1_policy_declares_recommended_action_never_genai(artifacts_dir):
    """BP7 makes no GenAI call anywhere (contrast BP6) - re-verified live against the real,
    currently saved Gate 1 policy.json rather than trusted from memory."""
    policy = _load_or_skip(artifacts_dir / "policy.json", "BP7 Gate 1")
    recommended_action_policy = policy["target_definition"]["output_fields"]["recommended_action"]
    assert "never genai" in recommended_action_policy.lower()


# --------------------------------------------------------------------------------------------
# Gate 5 decision-layer summary schema / real values
# --------------------------------------------------------------------------------------------


def test_gate5_summary_has_required_fields(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    required_fields = {
        "bp_id",
        "gate",
        "live_row_count",
        "champion_rule_scheme",
        "champion_weights_normalized",
        "intervention_threshold",
        "champion_stats",
        "contribution_decomposition_summary",
        "disparate_impact_audit",
        "recommended_action_breakdown",
        "records_csv_path",
    }
    missing = required_fields - set(summary.keys())
    assert not missing, f"gate5_decision_layer_summary.json is missing real fields: {missing}"


def test_gate5_genai_never_used(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    assert summary["compliance_touchpoint"]["genai_api_used"] is False


def test_gate5_contribution_reconstruction_exact(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    decomp = summary["contribution_decomposition_summary"]
    assert decomp["reconstruction_exact_within_tolerance"] is True


def test_gate5_recommended_action_breakdown_covers_full_population(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    breakdown = summary["recommended_action_breakdown"]
    n_covered = sum(row["n_rows"] for row in breakdown)
    assert n_covered == summary["live_row_count"]
    for row in breakdown:
        assert row["recommended_action"] in KNOWN_RECOMMENDED_ACTIONS


def test_gate5_weight_rederivation_matches_config(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    assert summary["weight_rederivation_cross_check"]["weights_match_config"] is True


# --------------------------------------------------------------------------------------------
# Cross-gate consistency (Gate 5's own real cross-checks against Gate 3/Gate 4)
# --------------------------------------------------------------------------------------------


def test_gate5_cross_checks_vs_gate3_gate4_all_passed(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    cross_checks = summary["cross_checks_vs_gate3_gate4"]
    assert cross_checks["coverage_pct_matches_gate3"] is True
    assert cross_checks["intervention_flag_rate_matches_gate4"] is True
    assert cross_checks["bp3_agreement_rate_matches_gate4"] is True


def test_gate3_champion_rule_scheme_matches_gate5(artifacts_dir):
    gate3 = _load_or_skip(artifacts_dir / "gate3_decision_rule_benchmark_summary.json", "BP7 Gate 3")
    gate5 = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    assert gate5["champion_rule_scheme"] == gate3["champion_rule_scheme"]


def test_gate4_leakage_reconfirmed_clean(artifacts_dir):
    gate4 = _load_or_skip(
        artifacts_dir / "gate4_statistical_validation_explainability_summary.json", "BP7 Gate 4"
    )
    assert gate4["leakage_reconfirmation"]["leakage_reconfirmed_clean"] is True


def test_gate4_contribution_reconstruction_exact(artifacts_dir):
    gate4 = _load_or_skip(
        artifacts_dir / "gate4_statistical_validation_explainability_summary.json", "BP7 Gate 4"
    )
    assert gate4["contribution_decomposition"]["reconstruction_exact_within_tolerance"] is True


# --------------------------------------------------------------------------------------------
# Gate 6's own governance artifacts
# --------------------------------------------------------------------------------------------


def test_gate6_governance_summary_reports_all_passed(artifacts_dir):
    """Real bug found+fixed 2026-09-25: this test's ORIGINAL `assert summary["pytest_all_passed"]
    is True` was a self-referential trap. gate6_governance_summary.json is written by the Gate 6
    notebook's own Section 12, which runs AFTER Section 7's real pytest subprocess call - the same
    subprocess call that evaluates THIS test. So at the moment this test runs, the summary file on
    disk can only ever be the one written by the PREVIOUS Gate 6 run, never the run currently in
    progress. Once any run's pytest genuinely failed for any real reason (as happened here from an
    unrelated bug, since fixed), every later run's own pytest subprocess would read that
    now-permanently-stale `pytest_all_passed=False` and fail this same test again - forever,
    regardless of whether every other real check in that later run actually passed. Confirmed
    real: BP6's own tests/bp6_genai_resolution_assistant/test_gate_artifacts.py has the identical
    pattern (same `is True` assertion) - dormant there only because BP6's pytest suite has never
    yet failed before its own first governance-summary write; not touched here since that BP is
    closed, per this project's own standing convention, but disclosed as a live latent risk.
    Fixed to check internal self-consistency of the persisted record instead of a value this test
    structurally cannot cause to ever recover through normal re-runs - a genuine data-integrity
    concern (do the recorded pass/fail count and the recorded boolean actually agree?) without the
    permanent trap.
    """
    summary = _load_or_skip(artifacts_dir / "gate6_governance_summary.json", "BP7 Gate 6")
    assert summary["pytest_all_passed"] == (summary["pytest_n_failed"] == 0), (
        f"gate6_governance_summary.json is internally inconsistent: pytest_all_passed="
        f"{summary['pytest_all_passed']!r} but pytest_n_failed={summary['pytest_n_failed']!r} "
        "(these two recorded fields disagree with each other - a real data-integrity bug, not "
        "the historical one-run-lag issue this test used to trip on)."
    )
    assert summary["notebook_syntax_all_passed"] is True
    assert summary["fastapi_self_test_all_checks_passed"] is True


def test_gate6_self_test_never_claims_a_real_external_api_call(artifacts_dir):
    """BP7's own honest self-test contract (contrast BP6): its self-test artifact must record
    zero real external API calls, since BP7 makes none anywhere."""
    self_test = _load_or_skip(artifacts_dir / "gate6_fastapi_self_test_result.json", "BP7 Gate 6")
    assert self_test.get("real_external_api_call_made") is False
    assert self_test["self_test_all_checks_passed"] is True


def test_gate6_self_test_result_never_overwrites_gate5_records(artifacts_dir):
    """The self-test artifact must stay a clearly scoped Gate 6 governance/testing record and must
    never overwrite or be confused with Gate 5's own full-population decision-records CSV."""
    self_test = _load_or_skip(artifacts_dir / "gate6_fastapi_self_test_result.json", "BP7 Gate 6")
    assert self_test["gate"] == 6

    gate5_summary = _load_or_skip(artifacts_dir / "gate5_decision_layer_summary.json", "BP7 Gate 5")
    assert gate5_summary["gate"] == 5  # Gate 5's own artifact, untouched by Gate 6


def test_gate6_config_block_and_report_files_exist(project_root, artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate6_governance_summary.json", "BP7 Gate 6")
    model_card_path = project_root / summary["model_card_path"]
    changelog_path = project_root / summary["changelog_path"]
    assert model_card_path.exists(), f"{model_card_path} does not exist"
    assert changelog_path.exists(), f"{changelog_path} does not exist"


def test_gate6_status_field_left_untouched(project_root):
    """BP7's own established convention (Gate 2, 3, 4, 5 all left it untouched): `status` is owned
    exclusively by Gate 1's own front-matter writer and is never touched by any gate-block writer,
    including this Gate 6's own. Checked live against the real, currently saved config file."""
    config_path = project_root / "configs" / "bp7_customer_navigator_decision_engine.yaml"
    if not config_path.exists():
        pytest.skip("BP7 config file does not exist.")
    config_text = config_path.read_text(encoding="utf-8")
    if "# --- Gate 6 (Productization" not in config_text:
        pytest.skip("BP7 Gate 6 has not been run for real yet.")
    import yaml

    config = yaml.safe_load(config_text)
    # Real, established BP7 convention: `status` is owned exclusively by Gate 1's own
    # front-matter writer, which legitimately derives it from read_existing_gate_block_markers()
    # (src/utils/bp1_config_sync.py) - so on a real, mature project `status` correctly grows to
    # e.g. "gate1_confirmed_gate2_confirmed_gate3_confirmed_..." as earlier gates complete and
    # Gate 1 is (or was) re-run. Asserting an exact literal here goes stale the moment that
    # happens (real incident, 2026-09-25: this exact assertion failed on a real run after Gates
    # 2-5 had genuinely completed - not a status-ownership violation). The invariant this test
    # actually needs to guard is narrower and doesn't require a hardcoded literal: Gate 6's own
    # gate-block writer must never be the one to add a "gate6" marker into status (only Gate 1's
    # own writer may ever do that, and it has never been asked to account for Gate 6).
    status_value = config["status"]
    assert status_value.startswith("gate1_confirmed") and "gate6" not in status_value.lower(), (
        f"BP7's status field is expected to still start with 'gate1_confirmed' and never contain "
        f"a 'gate6' marker (this project's own established convention: status is owned "
        f"exclusively by Gate 1's own front-matter writer, never touched by Gates 2-6's own "
        f"gate-block writers - Gate 1's own status derivation has never been asked to account for "
        f"Gate 6), but found {status_value!r}."
    )
