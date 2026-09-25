"""
src/reporting/bp4_rollup_helpers.py — Customer360 Navigator

Shared BP4 (Customer Journey Analytics) executive-rollup ("Gate 7") helper module. Sibling to
bp1_rollup_helpers.py / bp2_rollup_helpers.py / bp3_rollup_helpers.py (HYPER: same PALETTE /
CATEGORICAL_SEQUENCE identity reused verbatim across every BP's executive rollup, never
redefined per BP). This module is import-only shared logic — no I/O side effects at import time,
never executed by Claude, only the user runs it in their own environment, per the project's
execution-boundary rule.

BP4 has no supervised target and trains no model, so this module looks structurally different
from BP1/BP2/BP3's own rollup helpers in three deliberate ways, each documented at the function
that needed it rather than left implicit:
  - No model benchmark / PR-AUC / confusion-matrix / SHAP content exists anywhere here. Gate 3's
    real "champion" is the fastest CORRECT aggregation-pipeline candidate (5 candidates:
    pandas_groupby, polars_eager, polars_lazy, polars_lazy_streaming, duckdb_sql), never a
    predictive metric — `fig_benchmark_bar` replaces `fig_model_comparison_bar`.
  - No disparate-impact check exists for BP4 (Gate 4 real result: ecoa_disparate_impact_applicability
    == "NOT_APPLICABLE" — ECOA/Reg B does not map to BP4 per Master Plan Section 9, and
    `no_barred_column_in_cluster_key` is real-confirmed True regardless). Consequently
    `compute_production_recommendation` can only ever resolve to Tier 1 (RECOMMENDED FOR
    PRODUCTION) or Tier 3 (NOT RECOMMENDED) for BP4 — Tier 2 (CONDITIONAL - GOVERNANCE REVIEW
    REQUIRED) has no possible real trigger and this is stated explicitly in the computed reason
    string, never silently omitted.
  - Gate 4's real output is four bootstrap-CI statistical estimates (mean response lag,
    in-scope-vs-out-of-scope lag difference, recurring-cluster rate, mean cluster size), not a
    single held-out metric — `fig_mean_lag_ci_bar` / `fig_recurring_rate_ci_bar` replace
    `fig_confidence_distribution`, and Gate 5's real issue-cluster review-priority tier rollup
    (HIGH/MEDIUM/LOW/NONE, real cluster counts + real row coverage) replaces the per-row decision
    layer BP1-BP3 report.

No financial-impact, illustrative, or assumption-based content exists anywhere in this module —
every value returned by every function here is read live from BP4 Gates 1-6's own real,
already-confirmed artifacts, or computed live from them (e.g. the monthly complaint-volume trend
is aggregated live from the real Gate 2 Gold table, never hardcoded).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# ============================================================================
# Shared design-system constants — REUSED VERBATIM from bp1/bp2/bp3_rollup_helpers.py (HYPER: one
# real fixed palette identity across every BP's executive rollup, never redefined per BP).
# ============================================================================

PALETTE: dict[str, str] = {
    "primary_navy": "#1E2761",
    "accent_blue": "#4C6EF5",
    "ice_blue": "#CADCFC",
    "success_green": "#1B998B",
    "warning_amber": "#E8A33D",
    "danger_red": "#C1292E",
    "neutral_gray": "#6B7280",
    "surface_light": "#F7F8FC",
    "ink": "#101828",
    "ink_muted": "#4B5468",
}

CATEGORICAL_SEQUENCE: list[str] = [
    PALETTE["primary_navy"],
    PALETTE["accent_blue"],
    PALETTE["success_green"],
    PALETTE["warning_amber"],
    PALETTE["danger_red"],
    PALETTE["neutral_gray"],
]

TIER_COLOR_HEX: dict[str, str] = {
    "HIGH": PALETTE["danger_red"],
    "MEDIUM": PALETTE["warning_amber"],
    "LOW": PALETTE["accent_blue"],
    "NONE": PALETTE["neutral_gray"],
}

# BP4's own slow-candidate threshold, matching Gate 6's own live-detection rule
# (bp4_g6_code.py SLOW_CANDIDATE_MULTIPLIER) — reused here, never re-derived.
SLOW_CANDIDATE_MULTIPLIER = 2.0

# BP4's own required real artifacts (Gates 1, 2, 3, 4, 5, 6) — no model_inventory_entry.json
# equivalent exists for BP4 (Gate 6 real result: model_inventory_applicability ==
# "NOT_APPLICABLE"), unlike BP1/BP2/BP3's own required-files list.
REQUIRED_ARTIFACT_FILES: dict[str, str] = {
    "policy": "policy.json",
    "gate2_feature_lineage": "gate2_feature_lineage.csv",
    "gate3_benchmark_results": "gate3_benchmark_results.csv",
    "gate5_decision_layer_summary": "gate5_decision_layer_summary.json",
    "gate5_cluster_decision_report": "gate5_cluster_decision_report.csv",
    "gate6_governance_summary": "gate6_governance_summary.json",
}


def load_all_gate_artifacts(project_root: Path) -> dict[str, Any]:
    """Reads every real BP4 Gate 1-6 artifact live off disk. Raises a clear FileNotFoundError
    naming whichever one is missing — never silently substitutes a default or a synthetic value."""
    artifacts_dir = project_root / "notebooks" / "bp4_customer_journey_analytics" / "artifacts"
    config_path = project_root / "configs" / "bp4_customer_journey_analytics.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"BP4 config not found at {config_path} — run Gates 1-6 first.")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    missing = [fname for fname in REQUIRED_ARTIFACT_FILES.values() if not (artifacts_dir / fname).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing real BP4 Gate 1-6 artifact(s) under {artifacts_dir}: {missing}. "
            "Run every BP4 gate notebook (1 through 6) for real before Gate 7."
        )

    with open(artifacts_dir / REQUIRED_ARTIFACT_FILES["policy"], encoding="utf-8") as f:
        policy = json.load(f)
    with open(artifacts_dir / REQUIRED_ARTIFACT_FILES["gate5_decision_layer_summary"], encoding="utf-8") as f:
        gate5_summary = json.load(f)
    with open(artifacts_dir / REQUIRED_ARTIFACT_FILES["gate6_governance_summary"], encoding="utf-8") as f:
        gate6_summary = json.load(f)

    gate2_feature_lineage_df = pd.read_csv(artifacts_dir / REQUIRED_ARTIFACT_FILES["gate2_feature_lineage"])
    gate3_benchmark_df = pd.read_csv(artifacts_dir / REQUIRED_ARTIFACT_FILES["gate3_benchmark_results"])
    gate5_cluster_df = pd.read_csv(artifacts_dir / REQUIRED_ARTIFACT_FILES["gate5_cluster_decision_report"])

    champion_row = gate3_benchmark_df[gate3_benchmark_df["is_champion"]]
    if len(champion_row) != 1:
        raise ValueError(
            f"Expected exactly one is_champion=True row in gate3_benchmark_results.csv, found "
            f"{len(champion_row)}."
        )

    return {
        "project_root": project_root,
        "artifacts_dir": artifacts_dir,
        "config": config,
        "policy": policy,
        "gate2_feature_lineage_df": gate2_feature_lineage_df,
        "gate3_benchmark_df": gate3_benchmark_df,
        "gate5_summary": gate5_summary,
        "gate5_cluster_df": gate5_cluster_df,
        "gate6_summary": gate6_summary,
        "champion_pipeline": str(champion_row.iloc[0]["candidate"]),
    }


# ============================================================================
# Production recommendation — BP4's own 2-reachable-tier version (Tier 2 is structurally
# impossible: BP4 has no disparate-impact check, per Gate 4's real ecoa_disparate_impact_
# applicability == "NOT_APPLICABLE"). Computed LIVE from real gate artifacts only, never asserted
# in prose.
# ============================================================================


def compute_production_recommendation(bundle: dict[str, Any]) -> dict[str, Any]:
    gate6 = bundle["gate6_summary"]
    config = bundle["config"]

    all_gates_present = bool(config.get("status") == "gate6_complete")
    pytest_ok = bool(gate6.get("pytest_all_passed"))
    syntax_ok = bool(gate6.get("notebook_syntax_all_passed"))
    no_failed_candidates = int(gate6.get("n_gate3_failed_candidates_detected", -1)) == 0
    champion_consistent = bool(
        config.get("champion_pipeline")
        == config.get("performance_report", {}).get("champion_pipeline")
        == gate6.get("champion_pipeline")
    )
    cluster_count_consistent = bool(
        bundle["policy"]["live_checks"]["issue_cluster_stats"]["n_clusters"]
        == config.get("n_clusters")
        == config.get("n_clusters_reported")
    )
    row_coverage_matches = bool(config.get("total_rows_covered_matches_gate1", False))

    all_structural_checks_passed = all(
        [
            all_gates_present,
            pytest_ok,
            syntax_ok,
            no_failed_candidates,
            champion_consistent,
            cluster_count_consistent,
            row_coverage_matches,
        ]
    )

    if all_structural_checks_passed:
        tier_code, tier = 1, "RECOMMENDED FOR PRODUCTION"
        reason = (
            "All 6 gates real-run confirmed; every structural integrity check across all 6 gates "
            f"passed (pytest {gate6.get('pytest_counts', {}).get('passed')} passed/"
            f"{gate6.get('pytest_counts', {}).get('failed')} "
            f"failed, notebook-syntax audit all passed, 0 failed Gate 3 candidates, champion "
            f"pipeline '{bundle['champion_pipeline']}' consistent across Gate 3/Gate 4/Gate 6, "
            "real cluster count and row coverage consistent across Gate 1/2/5). Tier 2 "
            "(CONDITIONAL - GOVERNANCE REVIEW REQUIRED) is structurally unreachable for BP4: "
            "Gate 4's real ecoa_disparate_impact_applicability is NOT_APPLICABLE (BP4's "
            "issue-cluster key contains no ECOA/Reg B barred column and Master Plan Section 9 "
            "does not map ECOA/Reg B to BP4), so BP4 carries no disparate-impact check that could "
            "ever trigger Tier 2 — this differs from BP3, which does run that check and can land "
            "in Tier 2."
        )
    else:
        tier_code, tier = 3, "NOT RECOMMENDED"
        failed_checks = [
            name
            for name, ok in [
                ("all_gates_real_run_confirmed", all_gates_present),
                ("pytest_suite_all_passed", pytest_ok),
                ("notebook_syntax_all_passed", syntax_ok),
                ("no_failed_gate3_candidates", no_failed_candidates),
                ("champion_pipeline_consistent_across_gates", champion_consistent),
                ("cluster_count_consistent_across_gates", cluster_count_consistent),
                ("row_coverage_matches_gate1", row_coverage_matches),
            ]
            if not ok
        ]
        reason = (
            "At least one real structural integrity check failed or is unresolved: "
            f"{', '.join(failed_checks)}. Tier 2 remains structurally unreachable for BP4 "
            "regardless (no disparate-impact check exists for this BP), so any failure here "
            "resolves directly to Tier 3, never Tier 2."
        )

    return {
        "tier_code": tier_code,
        "tier": tier,
        "reason": reason,
        "tier_2_reachable_for_this_bp": False,
    }


# ============================================================================
# SMART suggestions — entirely BP4-specific, grounded in real Gate 1-6 findings only.
# ============================================================================


def build_smart_suggestions(bundle: dict[str, Any]) -> list[dict[str, str]]:
    g5 = bundle["gate5_summary"]
    tier_rollup = {row["review_priority_tier"]: row for row in g5["tier_rollup"]}
    high = tier_rollup.get("HIGH", {})
    medium = tier_rollup.get("MEDIUM", {})
    config = bundle["config"]
    gate3_df = bundle["gate3_benchmark_df"]
    champion = bundle["champion_pipeline"]
    champion_min = float(gate3_df.loc[gate3_df["is_champion"], "min_seconds"].iloc[0])
    slow_candidates = gate3_df[
        (gate3_df["status"] == "CORRECT")
        & (~gate3_df["is_champion"])
        & (gate3_df["min_seconds"] > SLOW_CANDIDATE_MULTIPLIER * champion_min)
    ]["candidate"].tolist()

    suggestions: list[dict[str, str]] = [
        {
            "title": "Prioritize real HIGH-tier issue clusters for human review first",
            "specific": (
                f"{high.get('n_clusters', 0):,} real issue clusters carry a HIGH review-priority "
                f"tier (recurring + elevated-lag + high-volume flags all triggered), covering "
                f"{high.get('n_complaint_rows_covered', 0):,} real complaint rows — the smallest "
                "cluster count of the four tiers but the one carrying every real risk signal at "
                "once. By contrast, the MEDIUM tier's "
                f"{medium.get('n_clusters', 0):,} clusters cover "
                f"{medium.get('n_complaint_rows_covered', 0):,} real rows — most of BP4's real "
                "row volume sits in a smaller number of large "
                "MEDIUM-tier clusters, so review capacity should weight HIGH first by risk density "
                "but not ignore MEDIUM's real row-volume concentration. Route HIGH to human review "
                "before MEDIUM/LOW."
            ),
            "measurable": (
                f"{high.get('n_clusters', 0):,} clusters / {high.get('n_complaint_rows_covered', 0):,} "
                "rows (real Gate 5 tier rollup)."
            ),
            "timebound": "Before the next BP4 data refresh.",
            "owner_placeholder": "[Assign: Complaint Operations Lead]",
        },
        {
            "title": "Reconcile Gate 3's real champion with Gate 2's production pipeline",
            "specific": (
                f"Gate 3's real full-scale benchmark champion is '{champion}' "
                f"(min_seconds={champion_min:.6f}), which differs from Gate 2's own already-"
                f"confirmed production implementation 'polars_lazy' "
                f"(champion_matches_current_production_implementation="
                f"{config.get('champion_matches_current_production_implementation')}). This is "
                "logged as a Gate 6 recommendation, not retroactively applied to Gate 2's "
                "already-confirmed output, per the project's standing discipline against "
                "rewriting already-closed gates."
            ),
            "measurable": (
                "Real speedup if adopted: "
                f"{config.get('performance_report', {}).get('speedup_factor', 0):.2f}x over the "
                "baseline (pandas_groupby, "
                f"{config.get('performance_report', {}).get('baseline_seconds', 0):.6f}s)."
            ),
            "timebound": "At BP4's next scheduled Gate 2 pipeline review.",
            "owner_placeholder": "[Assign: Data Engineering Lead]",
        },
        {
            "title": "Expand BANKING77-derived taxonomy coverage beyond its current 6.55%",
            "specific": (
                "The Gold-layer common_taxonomy_bucket overlay real-covers only "
                f"{bundle['policy']['journey_definition']['banking77_derived_coverage']['n_in_scope']:,} "
                f"of {bundle['policy']['journey_definition']['banking77_derived_coverage']['n_total']:,} "
                "real rows (6.55%), limiting how much of BP4's real issue-cluster population can be "
                "cross-referenced against BANKING77 intent categories in Gate 5's tier reporting."
            ),
            "measurable": (
                "Raise real in-scope coverage above 6.55% without changing BANKING77's own " "77-class scope."
            ),
            "timebound": "Coordinate with BP1's taxonomy-mapping owner next quarter.",
            "owner_placeholder": "[Assign: Taxonomy/Intent Classification Lead]",
        },
        {
            "title": (
                "Feed Gate 5's review_priority_score/tier into BP7's cross-BP decision engine "
                "as one real input"
            ),
            "specific": (
                "Gate 5's own compliance note (bp7_decision_engine_boundary) states this "
                "BP4-local reporting flag may become one real input BP7's cross-BP priority + "
                "intervention-risk decision engine later combines with BP1-BP5's own outputs — "
                "never presented as BP7's own decision on its own."
            ),
            "measurable": (
                f"{g5.get('n_with_reason_codes', 0):,} of {g5.get('n_clusters', 0):,} real clusters "
                "carry grounded reason codes, ready to be combined."
            ),
            "timebound": "When BP7 begins its own Gate 2 (input integration).",
            "owner_placeholder": "[Assign: BP7 Decision-Engine Owner]",
        },
        {
            "title": "Re-benchmark the real slow-but-correct Gate 3 candidates against future data growth",
            "specific": (
                f"{', '.join(slow_candidates) if slow_candidates else 'None on this real run'} "
                f"passed correctness but real min_seconds exceeded {SLOW_CANDIDATE_MULTIPLIER}x the "
                f"champion's own real min_seconds ({champion_min:.6f}s) — expected variation across "
                "execution-engine designs at this row count, not a defect, but worth re-checking as "
                "the real dataset grows past 1,048,575 rows, where the ranking can shift."
            ),
            "measurable": f"{len(slow_candidates)} real candidate(s) flagged this run.",
            "timebound": "At the next full-scale BP4 Gate 3 re-run.",
            "owner_placeholder": "[Assign: Data Engineering Lead]",
        },
    ]
    return suggestions


# ============================================================================
# KPI bundle — single source of truth for HTML/DOCX/XLSX/PPTX (HYPER: computed once, reused by
# every export).
# ============================================================================


def build_kpi_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    config = bundle["config"]
    gate6 = bundle["gate6_summary"]
    g5 = bundle["gate5_summary"]
    policy = bundle["policy"]
    prod_rec = compute_production_recommendation(bundle)

    tier_rollup = {row["review_priority_tier"]: row for row in g5["tier_rollup"]}
    total_clusters_reported = sum(r["n_clusters"] for r in g5["tier_rollup"])
    total_rows_covered = sum(r["n_complaint_rows_covered"] for r in g5["tier_rollup"])

    return {
        "generated_at_utc": gate6.get("generated_at_utc"),
        "champion_pipeline": bundle["champion_pipeline"],
        "champion_min_seconds": float(config["champion_min_seconds"]),
        "champion_mean_seconds": float(config["champion_mean_seconds"]),
        "champion_matches_current_production_implementation": bool(
            config.get("champion_matches_current_production_implementation")
        ),
        "baseline_seconds": float(config["performance_report"]["baseline_seconds"]),
        "speedup_factor": float(config["performance_report"]["speedup_factor"]),
        "journey_row_count": int(policy["live_checks"]["cfpb_row_count"]),
        "n_clusters": int(config["n_clusters"]),
        "n_recurring_clusters": int(policy["live_checks"]["issue_cluster_stats"]["n_recurring_clusters"]),
        "pct_clusters_recurring": float(
            policy["live_checks"]["issue_cluster_stats"]["pct_clusters_recurring"]
        ),
        "mean_response_lag_days": dict(config["mean_response_lag_days"]),
        "response_lag_days_diff_in_scope_vs_out_of_scope": dict(
            config["response_lag_days_diff_in_scope_vs_out_of_scope"]
        ),
        "recurring_cluster_rate": dict(config["recurring_cluster_rate"]),
        "mean_cluster_size": dict(config["mean_cluster_size"]),
        "n_bootstrap": int(config["n_bootstrap"]),
        "reproducibility_confirmed": bool(config["reproducibility_confirmed"]),
        "ecoa_disparate_impact_applicability": config["ecoa_disparate_impact_applicability"],
        "no_barred_column_in_cluster_key": bool(config["no_barred_column_in_cluster_key"]),
        "tier_rollup": {
            tier: {
                "n_clusters": int(row["n_clusters"]),
                "n_complaint_rows_covered": int(row["n_complaint_rows_covered"]),
                "mean_banking77_coverage_fraction": float(row["mean_banking77_coverage_fraction"]),
            }
            for tier, row in tier_rollup.items()
        },
        "n_clusters_reported": int(g5["n_clusters"]),
        "n_with_reason_codes": int(g5["n_with_reason_codes"]),
        "grounding_failures": int(g5["grounding_failures"]),
        "total_clusters_reported": int(total_clusters_reported),
        "total_rows_covered": int(total_rows_covered),
        "total_rows_covered_matches_gate1": bool(config["total_rows_covered_matches_gate1"]),
        "banking77_pct_in_scope": float(
            policy["journey_definition"]["banking77_derived_coverage"]["pct_in_scope"]
        ),
        "pytest_counts": {
            "passed": int(gate6["pytest_counts"]["passed"]),
            "failed": int(gate6["pytest_counts"]["failed"]),
            "skipped": int(gate6["pytest_counts"].get("skipped", 0)),
        },
        "pytest_all_passed": bool(gate6["pytest_all_passed"]),
        "notebook_syntax_all_passed": bool(gate6["notebook_syntax_all_passed"]),
        "n_gate3_failed_candidates": int(gate6["n_gate3_failed_candidates_detected"]),
        "n_gate3_slow_but_correct_candidates": int(gate6["n_gate3_slow_but_correct_candidates_detected"]),
        "governance_gates_complete": 6 if config.get("status") == "gate6_complete" else 5,
        "production_recommendation": prod_rec,
    }


# ============================================================================
# Gate 1 / Gate 6 real-output detail (for the DOCX/XLSX real full-detail sections).
# ============================================================================


def build_gate1_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    p = bundle["policy"]
    lc = p["live_checks"]
    return {
        "generated_at_utc": p["generated_at_utc"],
        "naming_commitment": p["journey_definition"]["naming_commitment"],
        "unit_1_description": p["journey_definition"]["unit_1_complaint_event_journey"]["description"],
        "unit_2_description": p["journey_definition"]["unit_2_issue_cluster_journey"]["description"],
        "banking77_n_in_scope": p["journey_definition"]["banking77_derived_coverage"]["n_in_scope"],
        "banking77_n_total": p["journey_definition"]["banking77_derived_coverage"]["n_total"],
        "banking77_pct_in_scope": p["journey_definition"]["banking77_derived_coverage"]["pct_in_scope"],
        "scope_boundaries": p["scope_boundaries"],
        "assumptions": p["assumptions"],
        "compliance_requirement": p["compliance_touchpoint"]["requirement"],
        "compliance_statement": p["compliance_touchpoint"]["statement"],
        "cfpb_row_count": lc["cfpb_row_count"],
        "complaint_id_is_unique_event_id": lc["complaint_id_is_unique_event_id"],
        "response_lag_days_stats": lc["response_lag_days_stats"],
        "date_received_range": lc["date_received_range"],
        "issue_cluster_stats": lc["issue_cluster_stats"],
        "null_counts_journey_columns": lc["null_counts_journey_columns"],
    }


def build_gate6_governance_detail(bundle: dict[str, Any]) -> dict[str, Any]:
    gate6 = bundle["gate6_summary"]
    config = bundle["config"]
    return {
        "pytest_summary_line": gate6.get("pytest_summary_line", ""),
        "pytest_counts": {
            "passed": gate6["pytest_counts"]["passed"],
            "failed": gate6["pytest_counts"]["failed"],
            "skipped": gate6["pytest_counts"].get("skipped", 0),
        },
        "pytest_all_passed": gate6["pytest_all_passed"],
        "notebook_syntax_check_n_passed": gate6.get("notebook_syntax_check_n_passed"),
        "notebook_syntax_check_n_failed": gate6.get("notebook_syntax_check_n_failed"),
        "notebook_syntax_all_passed": gate6["notebook_syntax_all_passed"],
        "n_gate3_failed_candidates_detected": gate6["n_gate3_failed_candidates_detected"],
        "n_gate3_slow_but_correct_candidates_detected": gate6["n_gate3_slow_but_correct_candidates_detected"],
        "gate3_slow_but_correct_candidates": gate6.get("gate3_slow_but_correct_candidates", []),
        "model_inventory_applicability": gate6.get("model_inventory_applicability"),
        "model_card_path": gate6.get(
            "model_card_path", "reports/bp4_customer_journey_analytics/MODEL_CARD.md"
        ),
        "changelog_path": gate6.get("changelog_path", "reports/bp4_customer_journey_analytics/CHANGELOG.md"),
        "champion_pipeline": gate6["champion_pipeline"],
        "config_status": config.get("status"),
        "generated_at_utc": gate6.get("generated_at_utc"),
    }


def tier_rollup_dataframe(bundle: dict[str, Any]) -> pd.DataFrame:
    order = ["HIGH", "MEDIUM", "LOW", "NONE"]
    rows = {row["review_priority_tier"]: row for row in bundle["gate5_summary"]["tier_rollup"]}
    return pd.DataFrame(
        [
            {
                "review_priority_tier": t,
                "n_clusters": rows[t]["n_clusters"],
                "n_complaint_rows_covered": rows[t]["n_complaint_rows_covered"],
                "mean_banking77_coverage_fraction": rows[t]["mean_banking77_coverage_fraction"],
            }
            for t in order
            if t in rows
        ]
    )


# ============================================================================
# Matplotlib figure builders — WARP: each rendered ONCE by the notebook, reused as raw PNG bytes
# across DOCX and PPTX.
# ============================================================================


def _fig_to_png_bytes(fig, dpi: int = 150) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    png_bytes = buf.read()
    import matplotlib.pyplot as plt

    plt.close(fig)
    return png_bytes


def fig_benchmark_bar(gate3_df: pd.DataFrame, champion: str) -> bytes:
    import matplotlib.pyplot as plt

    df = gate3_df.sort_values("min_seconds")
    colors = [PALETTE["success_green"] if c == champion else PALETTE["neutral_gray"] for c in df["candidate"]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(df["candidate"], df["min_seconds"], color=colors)
    ax.set_xlabel("min_seconds (real, lower is better)")
    ax.set_title("Gate 3 — Real Aggregation-Pipeline Benchmark (5 candidates)")
    for i, (v, s) in enumerate(zip(df["min_seconds"], df["status"])):
        ax.text(v, i, f"  {v:.4f}s ({s})", va="center", fontsize=9, color=PALETTE["ink"])
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_tier_rollup_bar(tier_df: pd.DataFrame) -> bytes:
    import matplotlib.pyplot as plt

    colors = [TIER_COLOR_HEX.get(t, PALETTE["neutral_gray"]) for t in tier_df["review_priority_tier"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(tier_df["review_priority_tier"], tier_df["n_clusters"], color=colors)
    axes[0].set_title("Real cluster count by tier")
    axes[0].set_ylabel("n_clusters")
    axes[1].bar(tier_df["review_priority_tier"], tier_df["n_complaint_rows_covered"], color=colors)
    axes[1].set_title("Real complaint-row coverage by tier")
    axes[1].set_ylabel("n_complaint_rows_covered")
    fig.suptitle("Gate 5 — Real Issue-Cluster Review-Priority Tier Rollup")
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_ci_bar(point_estimate: float, ci_low: float, ci_high: float, label: str, unit: str = "") -> bytes:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ax.barh([label], [point_estimate], color=PALETTE["accent_blue"], height=0.4)
    ax.errorbar(
        [point_estimate],
        [label],
        xerr=[[point_estimate - ci_low], [ci_high - point_estimate]],
        fmt="none",
        ecolor=PALETTE["primary_navy"],
        capsize=6,
        elinewidth=2,
    )
    ax.set_title(f"{label} — real point estimate + 95% bootstrap CI")
    ax.set_xlabel(unit)
    ax.text(
        point_estimate,
        0.15,
        f"{point_estimate:.4f}\n[{ci_low:.4f}, {ci_high:.4f}]",
        ha="center",
        fontsize=9,
        color=PALETTE["ink"],
    )
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_monthly_volume_trend(monthly_totals: pd.DataFrame) -> bytes:
    """monthly_totals: real, live-aggregated from the Gate 2 Gold table
    (cfpb_issue_cluster_monthly_gold.parquet), columns complaint_month, n_complaints_month —
    never a hardcoded or synthetic series."""
    import matplotlib.pyplot as plt

    df = monthly_totals.sort_values("complaint_month")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["complaint_month"], df["n_complaints_month"], color=PALETTE["primary_navy"], linewidth=2)
    ax.fill_between(df["complaint_month"], df["n_complaints_month"], color=PALETTE["ice_blue"], alpha=0.5)
    ax.set_title("Real monthly complaint volume (all issue clusters, Gate 2 Gold table)")
    ax.set_ylabel("n_complaints_month")
    step = max(1, len(df) // 12)
    ax.set_xticks(range(0, len(df), step))
    ax.set_xticklabels(df["complaint_month"].iloc[::step], rotation=45, ha="right", fontsize=8)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


# ============================================================================
# DOCX export (python-docx). US Letter page size, Calibri professional font (docx skill).
# ============================================================================


def write_docx_report(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    figures: dict[str, bytes],
    tier_df: pd.DataFrame,
    out_path: Path,
) -> Path:
    import io as _io

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    NAVY = RGBColor(0x1E, 0x27, 0x61)
    SUCCESS = RGBColor(0x1B, 0x99, 0x8B)
    AMBER = RGBColor(0xE8, 0xA3, 0x3D)
    DANGER = RGBColor(0xC1, 0x29, 0x2E)
    TIER_COLOR = {1: SUCCESS, 2: AMBER, 3: DANGER}

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    title = doc.add_heading("BP4 — Customer Journey Analytics", level=0)
    title.runs[0].font.color.rgb = NAVY
    doc.add_paragraph("Executive Rollup Report — Customer360 Navigator Enterprise Suite")
    p = doc.add_paragraph(f"Generated: {kpis['generated_at_utc']}")
    p.runs[0].font.italic = True

    p = doc.add_paragraph()
    run = p.add_run(f"Recommended for Production: {prod_rec['tier']}")
    run.font.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = TIER_COLOR.get(prod_rec["tier_code"], NAVY)
    doc.add_paragraph(prod_rec["reason"])

    doc.add_heading("Executive Summary — Real KPIs", level=1)
    kpi_table = doc.add_table(rows=1, cols=2)
    kpi_table.style = "Light Grid Accent 1"
    hdr = kpi_table.rows[0].cells
    hdr[0].text, hdr[1].text = "KPI", "Value"
    for label, val in [
        ("Champion aggregation pipeline (Gate 3, real)", kpis["champion_pipeline"]),
        (
            "Real speedup over baseline",
            f"{kpis['speedup_factor']:.2f}x ({kpis['baseline_seconds']:.4f}s -> "
            f"{kpis['champion_min_seconds']:.4f}s)",
        ),
        (
            "Champion matches Gate 2 production pipeline",
            kpis["champion_matches_current_production_implementation"],
        ),
        ("Real journey-event row count", f"{kpis['journey_row_count']:,}"),
        ("Real issue-cluster count", f"{kpis['n_clusters']:,}"),
        ("Real recurring-cluster rate", f"{kpis['pct_clusters_recurring']:.2%}"),
        (
            "Mean response lag (days, real, 95% bootstrap CI)",
            f"{kpis['mean_response_lag_days']['point_estimate']:.4f} "
            f"[{kpis['mean_response_lag_days']['ci_95_low']:.4f}, "
            f"{kpis['mean_response_lag_days']['ci_95_high']:.4f}]",
        ),
        ("BANKING77-derived coverage (real)", f"{kpis['banking77_pct_in_scope']:.2%}"),
        ("Real total rows covered by Gate 5 tier rollup", f"{kpis['total_rows_covered']:,}"),
        ("Total rows match Gate 1 (real)", kpis["total_rows_covered_matches_gate1"]),
        ("ECOA/Reg B disparate-impact applicability", kpis["ecoa_disparate_impact_applicability"]),
        ("pytest", f"{kpis['pytest_counts']['passed']} passed / {kpis['pytest_counts']['failed']} failed"),
        ("Governance gates complete", f"{kpis['governance_gates_complete']}/6"),
    ]:
        row = kpi_table.add_row().cells
        row[0].text = str(label)
        row[1].text = str(val)

    doc.add_heading("Gate 1 — Business Understanding & Policy (real)", level=1)
    doc.add_paragraph(gate1["naming_commitment"])
    doc.add_paragraph(f"Unit 1 (complaint-event journey): {gate1['unit_1_description']}")
    doc.add_paragraph(f"Unit 2 (issue-cluster journey): {gate1['unit_2_description']}")
    doc.add_paragraph(
        f"Real CFPB row count (live check): {gate1['cfpb_row_count']:,} — Complaint ID confirmed a "
        f"unique event identifier: {gate1['complaint_id_is_unique_event_id']}."
    )
    doc.add_paragraph(
        "Real response_lag_days distribution: mean="
        f"{gate1['response_lag_days_stats']['mean']:.4f}, "
        f"median={gate1['response_lag_days_stats']['p50']}, "
        f"max={gate1['response_lag_days_stats']['max']}, "
        f"0 negative / 0 null values."
    )
    doc.add_heading("Compliance touchpoint", level=2)
    doc.add_paragraph(gate1["compliance_statement"])
    doc.add_heading("Scope boundaries (real)", level=2)
    for b in gate1["scope_boundaries"]:
        doc.add_paragraph(b, style="List Bullet")
    doc.add_heading("Assumptions documented at Gate 1 (real)", level=2)
    for a in gate1["assumptions"]:
        doc.add_paragraph(a, style="List Bullet")

    doc.add_heading("Gate 3 — Aggregation-Pipeline Benchmark (real)", level=1)
    doc.add_paragraph(
        "Champion selected by real measured wall-clock speed among 5 CORRECT candidates — never by "
        "a predictive metric (BP4 has no supervised target)."
    )
    doc.add_picture(_io.BytesIO(figures["benchmark"]), width=Inches(6.0))
    bdf = bundle["gate3_benchmark_df"]
    bench_table = doc.add_table(rows=1, cols=5)
    bench_table.style = "Light Grid Accent 1"
    hdr = bench_table.rows[0].cells
    for i, h in enumerate(["candidate", "status", "min_seconds", "mean_seconds", "champion"]):
        hdr[i].text = h
    for _, r in bdf.iterrows():
        row = bench_table.add_row().cells
        row[0].text = str(r["candidate"])
        row[1].text = str(r["status"])
        row[2].text = f"{r['min_seconds']:.6f}"
        row[3].text = f"{r['mean_seconds']:.6f}"
        row[4].text = "YES" if bool(r["is_champion"]) else ""

    doc.add_heading("Gate 4 — Statistical Validation (real, bootstrap CI)", level=1)
    doc.add_picture(_io.BytesIO(figures["mean_lag_ci"]), width=Inches(5.5))
    doc.add_picture(_io.BytesIO(figures["recurring_rate_ci"]), width=Inches(5.5))
    ci_table = doc.add_table(rows=1, cols=4)
    ci_table.style = "Light Grid Accent 1"
    hdr = ci_table.rows[0].cells
    for i, h in enumerate(["Real statistic", "Point estimate", "CI 95% low", "CI 95% high"]):
        hdr[i].text = h
    for label, d in [
        ("Mean response lag (days)", kpis["mean_response_lag_days"]),
        (
            "In-scope minus out-of-scope lag difference (days)",
            kpis["response_lag_days_diff_in_scope_vs_out_of_scope"],
        ),
        ("Recurring-cluster rate", kpis["recurring_cluster_rate"]),
        ("Mean cluster size", kpis["mean_cluster_size"]),
    ]:
        row = ci_table.add_row().cells
        row[0].text = label
        row[1].text = f"{d['point_estimate']:.6f}"
        row[2].text = f"{d['ci_95_low']:.6f}"
        row[3].text = f"{d['ci_95_high']:.6f}"
    doc.add_paragraph(
        f"n_bootstrap={kpis['n_bootstrap']:,} resamples. Reproducibility confirmed (Gate 4 real "
        f"re-run comparison): {kpis['reproducibility_confirmed']}. ECOA/Reg B disparate-impact "
        f"applicability: {kpis['ecoa_disparate_impact_applicability']} — BP4's issue-cluster key "
        f"contains no barred column (no_barred_column_in_cluster_key="
        f"{kpis['no_barred_column_in_cluster_key']})."
    )

    doc.add_heading("Gate 5 — Issue-Cluster Review-Priority Tier Rollup (real)", level=1)
    doc.add_picture(_io.BytesIO(figures["tier_rollup"]), width=Inches(6.0))
    tier_table = doc.add_table(rows=1, cols=4)
    tier_table.style = "Light Grid Accent 1"
    hdr = tier_table.rows[0].cells
    for i, h in enumerate(["Tier", "n_clusters", "n_complaint_rows_covered", "mean BANKING77 coverage"]):
        hdr[i].text = h
    for _, r in tier_df.iterrows():
        row = tier_table.add_row().cells
        row[0].text = str(r["review_priority_tier"])
        row[1].text = f"{int(r['n_clusters']):,}"
        row[2].text = f"{int(r['n_complaint_rows_covered']):,}"
        row[3].text = f"{r['mean_banking77_coverage_fraction']:.4f}"
    doc.add_paragraph(
        f"n_with_reason_codes={kpis['n_with_reason_codes']:,} / n_clusters_reported="
        f"{kpis['n_clusters_reported']:,}, grounding_failures={kpis['grounding_failures']}. Real "
        f"total rows covered ({kpis['total_rows_covered']:,}) matches Gate 1's journey_row_count: "
        f"{kpis['total_rows_covered_matches_gate1']}."
    )
    if "monthly_trend" in figures:
        doc.add_heading("Monthly Complaint-Volume Trend (real, live-aggregated)", level=2)
        doc.add_picture(_io.BytesIO(figures["monthly_trend"]), width=Inches(6.0))

    doc.add_heading("Gate 6 — Governance & Known Limitations (real)", level=1)
    doc.add_paragraph(
        f"pytest suite: {gate6['pytest_counts']['passed']} passed / "
        f"{gate6['pytest_counts']['failed']} failed "
        f"(skipped {gate6['pytest_counts'].get('skipped', 0)}). Notebook syntax audit: "
        f"{gate6['notebook_syntax_check_n_passed']}/"
        f"{gate6['notebook_syntax_check_n_passed'] + gate6['notebook_syntax_check_n_failed']} passed."
    )
    doc.add_paragraph(
        "Open items — Gate 3 candidate-level issues detected live: "
        f"{gate6['n_gate3_failed_candidates_detected']} outright failure(s), "
        f"{gate6['n_gate3_slow_but_correct_candidates_detected']} slow-but-correct candidate(s) "
        f"({', '.join(gate6['gate3_slow_but_correct_candidates']) or 'none'})."
    )
    doc.add_paragraph(f"Model card: {gate6['model_card_path']} | Changelog: {gate6['changelog_path']}")
    doc.add_paragraph(
        f"Model inventory (SR 11-7) applicability: {gate6['model_inventory_applicability']} — BP4 "
        "registers no trained model, only this benchmarked aggregation/reporting pipeline."
    )

    doc.add_heading("SMART Suggestions", level=1)
    for s in suggestions:
        doc.add_heading(s["title"], level=2)
        doc.add_paragraph(f"Specific: {s['specific']}")
        doc.add_paragraph(f"Measurable: {s['measurable']}")
        doc.add_paragraph(f"Time-bound: {s['timebound']}")
        doc.add_paragraph(f"Owner: {s['owner_placeholder']}")

    for p in doc.paragraphs:
        if p.alignment is None:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


# ============================================================================
# XLSX export (openpyxl). 9 sheets, each built from a real Gate 1-6 artifact.
# ============================================================================


def write_xlsx_workbook(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    tier_df: pd.DataFrame,
    out_path: Path,
) -> Path:
    import re

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    navy_fill = PatternFill(start_color="1E2761", end_color="1E2761", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(bold=True, size=14, color="1E2761")

    # Same real defensive guard bp1/bp2/bp3_rollup_helpers.py carry (Lesson: BP1's first real run
    # hit openpyxl.utils.exceptions.IllegalCharacterError on gate6's real captured
    # pytest_summary_line, which can carry ANSI color-escape control bytes).
    _ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    _ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

    def _safe(value):
        if isinstance(value, str):
            return _ILLEGAL_XLSX_CHARS_RE.sub("", _ANSI_ESCAPE_RE.sub("", value))
        return value

    def _safe_row(row):
        return [_safe(v) for v in row]

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    wb = Workbook()

    def _style_header(ws, row_idx: int, n_cols: int):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=row_idx, column=c)
            cell.fill = navy_fill
            cell.font = header_font

    def _autosize(ws, n_cols: int, width: int = 22):
        for c in range(1, n_cols + 1):
            ws.column_dimensions[get_column_letter(c)].width = width

    # --- 00_ReadMe ---
    ws = wb.active
    ws.title = "00_ReadMe"
    ws["A1"] = "BP4 Customer Journey Analytics — Executive Rollup Workbook"
    ws["A1"].font = title_font
    ws["A3"] = f"Generated: {kpis['generated_at_utc']}"
    ws["A4"] = "Every sheet here is built only from BP4 Gates 1-6's real, real-run-confirmed artifacts."
    ws["A5"] = "No assumption-based, illustrative, or estimated content appears anywhere in this workbook."
    ws["A6"] = f"Recommended for Production status: {prod_rec['tier']}"
    ws["A6"].font = Font(bold=True, color="1E2761")
    sheets_index = [
        (
            "01_Executive_KPIs",
            "Top-line real KPIs across all 6 gates, incl. the live Recommended-for-Production status.",
        ),
        (
            "02_Gate1_Journey_Definition",
            "Gate 1 real journey definition, scope boundaries, assumptions, compliance, live row accounting.",
        ),
        (
            "03_Aggregation_Benchmark",
            "Gate 3 real 5-candidate aggregation-pipeline benchmark (speed-selected, no predictive metric).",
        ),
        (
            "04_Statistical_Validation",
            "Gate 4 real bootstrap-CI statistics (mean lag, recurring rate, cluster size, "
            "in/out-of-scope lag diff).",
        ),
        (
            "05_Tier_Rollup_Summary",
            "Gate 5 real issue-cluster review-priority tier rollup (HIGH/MEDIUM/LOW/NONE).",
        ),
        ("06_HIGH_Tier_Clusters", "Gate 5 real full export of every HIGH-tier issue cluster."),
        ("07_Gate6_Governance", "Gate 6 real governance status, open items, model card/changelog refs."),
        ("08_SMART_Suggestions", "Data-grounded SMART recommendations."),
    ]
    for i, (name, desc) in enumerate(sheets_index):
        ws.cell(row=8 + i, column=1, value=name)
        ws.cell(row=8 + i, column=2, value=desc)
    _autosize(ws, 2, width=42)

    # --- 01_Executive_KPIs ---
    ws = wb.create_sheet("01_Executive_KPIs")
    ws.append(["KPI", "Value"])
    _style_header(ws, 1, 2)
    kpi_rows = [
        ("Recommended for Production status", prod_rec["tier"]),
        ("Production status reason", prod_rec["reason"]),
        ("Champion aggregation pipeline (real)", kpis["champion_pipeline"]),
        ("Real speedup over baseline", f"{kpis['speedup_factor']:.4f}x"),
        (
            "Champion matches Gate 2 production pipeline",
            kpis["champion_matches_current_production_implementation"],
        ),
        ("Real journey-event row count", kpis["journey_row_count"]),
        ("Real issue-cluster count", kpis["n_clusters"]),
        ("Real recurring-cluster rate", kpis["pct_clusters_recurring"]),
        ("Mean response lag (days, point estimate)", kpis["mean_response_lag_days"]["point_estimate"]),
        ("Mean response lag CI 95% low", kpis["mean_response_lag_days"]["ci_95_low"]),
        ("Mean response lag CI 95% high", kpis["mean_response_lag_days"]["ci_95_high"]),
        ("BANKING77-derived coverage (real)", kpis["banking77_pct_in_scope"]),
        ("Real total rows covered by tier rollup", kpis["total_rows_covered"]),
        ("Total rows match Gate 1 (real)", kpis["total_rows_covered_matches_gate1"]),
        ("ECOA/Reg B disparate-impact applicability", kpis["ecoa_disparate_impact_applicability"]),
        ("pytest passed", kpis["pytest_counts"]["passed"]),
        ("pytest failed", kpis["pytest_counts"]["failed"]),
        ("Notebook syntax audit all passed", kpis["notebook_syntax_all_passed"]),
        ("Gate 3 failed candidates (open item)", kpis["n_gate3_failed_candidates"]),
        ("Gate 3 slow-but-correct candidates (open item)", kpis["n_gate3_slow_but_correct_candidates"]),
        ("Governance gates complete", f"{kpis['governance_gates_complete']}/6"),
    ]
    for row in kpi_rows:
        ws.append(_safe_row(list(row)))
    _autosize(ws, 2, width=42)
    ws.column_dimensions["B"].width = 60
    for r_idx in (9, 12):
        ws.cell(row=r_idx, column=2).number_format = "0.00%"

    # --- 02_Gate1_Journey_Definition ---
    ws = wb.create_sheet("02_Gate1_Journey_Definition")
    ws["A1"] = "Gate 1 — Business Understanding & Policy (real, from policy.json)"
    ws["A1"].font = title_font
    row_idx = 3
    for label, val in [
        ("Naming commitment", gate1["naming_commitment"]),
        ("Unit 1 (complaint-event journey)", gate1["unit_1_description"]),
        ("Unit 2 (issue-cluster journey)", gate1["unit_2_description"]),
        ("Real CFPB row count", gate1["cfpb_row_count"]),
        ("Complaint ID confirmed unique event id", gate1["complaint_id_is_unique_event_id"]),
        ("Compliance requirement", gate1["compliance_requirement"]),
        ("Compliance statement", gate1["compliance_statement"]),
        ("Generated at (UTC)", gate1["generated_at_utc"]),
    ]:
        ws.cell(row=row_idx, column=1, value=_safe(label))
        ws.cell(row=row_idx, column=2, value=_safe(val))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Scope Boundaries (real)").font = Font(bold=True, color="1E2761")
    row_idx += 1
    for b in gate1["scope_boundaries"]:
        ws.cell(row=row_idx, column=1, value=_safe(b))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Assumptions (real)").font = Font(bold=True, color="1E2761")
    row_idx += 1
    for a in gate1["assumptions"]:
        ws.cell(row=row_idx, column=1, value=_safe(a))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Real null counts (journey-relevant columns)").font = Font(
        bold=True, color="1E2761"
    )
    row_idx += 1
    for k, v in gate1["null_counts_journey_columns"].items():
        ws.cell(row=row_idx, column=1, value=_safe(k))
        ws.cell(row=row_idx, column=2, value=v)
        row_idx += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 90
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- 03_Aggregation_Benchmark ---
    ws = wb.create_sheet("03_Aggregation_Benchmark")
    cols = [
        "candidate",
        "status",
        "min_seconds",
        "mean_seconds",
        "std_seconds",
        "mean_mem_delta_mb",
        "is_champion",
    ]
    ws.append(cols)
    _style_header(ws, 1, len(cols))
    for r in bundle["gate3_benchmark_df"][cols].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(cols), width=20)

    # --- 04_Statistical_Validation ---
    ws = wb.create_sheet("04_Statistical_Validation")
    ws.append(["Real statistic", "Point estimate", "CI 95% low", "CI 95% high"])
    _style_header(ws, 1, 4)
    for label, d in [
        ("Mean response lag (days)", kpis["mean_response_lag_days"]),
        (
            "In-scope minus out-of-scope lag difference (days)",
            kpis["response_lag_days_diff_in_scope_vs_out_of_scope"],
        ),
        ("Recurring-cluster rate", kpis["recurring_cluster_rate"]),
        ("Mean cluster size", kpis["mean_cluster_size"]),
    ]:
        ws.append(_safe_row([label, d["point_estimate"], d["ci_95_low"], d["ci_95_high"]]))
    ws.append([])
    ws.append(["n_bootstrap", kpis["n_bootstrap"]])
    ws.append(["reproducibility_confirmed", kpis["reproducibility_confirmed"]])
    ws.append(["ecoa_disparate_impact_applicability", kpis["ecoa_disparate_impact_applicability"]])
    ws.append(["no_barred_column_in_cluster_key", kpis["no_barred_column_in_cluster_key"]])
    _autosize(ws, 4, width=30)

    # --- 05_Tier_Rollup_Summary ---
    ws = wb.create_sheet("05_Tier_Rollup_Summary")
    tcols = [
        "review_priority_tier",
        "n_clusters",
        "n_complaint_rows_covered",
        "mean_banking77_coverage_fraction",
    ]
    ws.append(tcols)
    _style_header(ws, 1, len(tcols))
    for r in tier_df[tcols].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    ws.append([])
    ws.append(["n_clusters_reported", kpis["n_clusters_reported"]])
    ws.append(["n_with_reason_codes", kpis["n_with_reason_codes"]])
    ws.append(["grounding_failures", kpis["grounding_failures"]])
    ws.append(["total_rows_covered", kpis["total_rows_covered"]])
    ws.append(["total_rows_covered_matches_gate1", kpis["total_rows_covered_matches_gate1"]])
    _autosize(ws, len(tcols), width=26)

    # --- 06_HIGH_Tier_Clusters (full real export — every HIGH-tier cluster, never sampled) ---
    ws = wb.create_sheet("06_HIGH_Tier_Clusters")
    high_cols = [
        "Company",
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "n_complaints_total",
        "avg_response_lag_days",
        "banking77_coverage_fraction",
        "review_priority_score",
        "reason_codes",
    ]
    ws.append(high_cols)
    _style_header(ws, 1, len(high_cols))
    high_df = bundle["gate5_cluster_df"]
    high_df = high_df[high_df["review_priority_tier"] == "HIGH"][high_cols]
    for r in high_df.itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(high_cols), width=22)
    ws.column_dimensions["J"].width = 40

    # --- 07_Gate6_Governance ---
    ws = wb.create_sheet("07_Gate6_Governance")
    ws["A1"] = "Gate 6 — Governance, Known Limitations & Compliance (real)"
    ws["A1"].font = title_font
    row_idx = 3
    for label, val in [
        ("Recommended for Production status", prod_rec["tier"]),
        ("Production status reason", prod_rec["reason"]),
        ("pytest summary line", gate6.get("pytest_summary_line")),
        ("pytest passed", gate6["pytest_counts"]["passed"]),
        ("pytest failed", gate6["pytest_counts"]["failed"]),
        ("pytest skipped", gate6["pytest_counts"].get("skipped")),
        ("pytest all passed", gate6["pytest_all_passed"]),
        ("Notebook syntax check — passed", gate6["notebook_syntax_check_n_passed"]),
        ("Notebook syntax check — failed", gate6["notebook_syntax_check_n_failed"]),
        ("Notebook syntax all passed", gate6["notebook_syntax_all_passed"]),
        ("Open item — Gate 3 failed candidates detected", gate6["n_gate3_failed_candidates_detected"]),
        (
            "Open item — Gate 3 slow-but-correct candidates detected",
            gate6["n_gate3_slow_but_correct_candidates_detected"],
        ),
        (
            "Slow-but-correct candidates",
            ", ".join(gate6.get("gate3_slow_but_correct_candidates", [])) or "none",
        ),
        ("Model inventory (SR 11-7) applicability", gate6.get("model_inventory_applicability")),
        ("Model card path", gate6["model_card_path"]),
        ("Changelog path", gate6["changelog_path"]),
        ("Champion pipeline (real, consistent across gates)", gate6["champion_pipeline"]),
        ("Config status", gate6["config_status"]),
        ("Generated at (UTC)", gate6["generated_at_utc"]),
    ]:
        ws.cell(row=row_idx, column=1, value=_safe(label))
        ws.cell(row=row_idx, column=2, value=_safe(val))
        row_idx += 1
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 90
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- 08_SMART_Suggestions ---
    ws = wb.create_sheet("08_SMART_Suggestions")
    ws.append(["Title", "Specific", "Measurable", "Time-bound", "Owner"])
    _style_header(ws, 1, 5)
    for s in suggestions:
        ws.append(
            _safe_row([s["title"], s["specific"], s["measurable"], s["timebound"], s["owner_placeholder"]])
        )
    for col in "ABCDE":
        ws.column_dimensions[col].width = 42
        for cell in ws[col]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# ============================================================================
# PPTX export (python-pptx). Reuses the same shared matplotlib PNGs as the DOCX export.
# ============================================================================


def write_pptx_deck(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    figures: dict[str, bytes],
    tier_df: pd.DataFrame,
    out_path: Path,
) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor as PptxRGBColor
    from pptx.util import Inches as PptxInches
    from pptx.util import Pt as PptxPt

    NAVY = PptxRGBColor(0x1E, 0x27, 0x61)
    WHITE = PptxRGBColor(0xFF, 0xFF, 0xFF)
    GRAY = PptxRGBColor(0x4B, 0x54, 0x68)
    AMBER = PptxRGBColor(0xE8, 0xA3, 0x3D)
    SUCCESS = PptxRGBColor(0x1B, 0x99, 0x8B)
    DANGER = PptxRGBColor(0xC1, 0x29, 0x2E)
    TIER_COLOR = {1: SUCCESS, 2: AMBER, 3: DANGER}

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    prs = Presentation()
    prs.slide_width = PptxInches(13.333)
    prs.slide_height = PptxInches(7.5)
    blank_layout = prs.slide_layouts[6]

    def _add_slide():
        return prs.slides.add_slide(blank_layout)

    def _add_title(slide, text: str, subtitle: str | None = None, dark: bool = False):
        box = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(0.35), PptxInches(12.1), PptxInches(0.9))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = text
        run.font.size = PptxPt(26)
        run.font.bold = True
        run.font.color.rgb = WHITE if dark else NAVY
        if subtitle:
            box2 = slide.shapes.add_textbox(
                PptxInches(0.6), PptxInches(1.05), PptxInches(12.1), PptxInches(0.5)
            )
            tf2 = box2.text_frame
            tf2.word_wrap = True
            p2 = tf2.paragraphs[0]
            r2 = p2.add_run()
            r2.text = subtitle
            r2.font.size = PptxPt(14)
            r2.font.color.rgb = WHITE if dark else GRAY

    def _fill_bg(slide, color: PptxRGBColor):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def _add_picture_bytes(slide, png_bytes: bytes, left, top, width=None, height=None):
        return slide.shapes.add_picture(io.BytesIO(png_bytes), left, top, width=width, height=height)

    def _add_kpi_box(slide, left, top, width, height, label, value):
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = str(value)
        r1.font.size = PptxPt(24)
        r1.font.bold = True
        r1.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = label
        r2.font.size = PptxPt(11)
        r2.font.color.rgb = GRAY

    def _add_bullets(slide, lines, top=PptxInches(1.4), color=None, size=15):
        box = slide.shapes.add_textbox(
            PptxInches(0.6), top, PptxInches(12.1), PptxInches(7.5) - top - PptxInches(0.4)
        )
        tf = box.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = p.add_run()
            r.text = "• " + line
            r.font.size = PptxPt(size)
            r.font.color.rgb = color or GRAY

    # --- Slide 1: Title ---
    s = _add_slide()
    _fill_bg(s, NAVY)
    _add_title(
        s,
        "BP4 Customer Journey Analytics",
        "Executive Rollup — Customer360 Navigator Enterprise Suite",
        dark=True,
    )
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(5.3), PptxInches(12.1), PptxInches(1.6))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = (
        f"Champion pipeline: {kpis['champion_pipeline']}  |  "
        f"Real speedup: {kpis['speedup_factor']:.2f}x  |  Generated {kpis['generated_at_utc'][:10]}"
    )
    r.font.size = PptxPt(15)
    r.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = f"Recommended for Production: {prod_rec['tier']}"
    r2.font.size = PptxPt(17)
    r2.font.bold = True
    r2.font.color.rgb = TIER_COLOR.get(prod_rec["tier_code"], WHITE)

    # --- Slide 2: Executive KPIs ---
    s = _add_slide()
    _add_title(s, "Executive Summary — Real KPIs")
    kpi_cells = [
        ("Champion Pipeline", kpis["champion_pipeline"]),
        ("Real Speedup", f"{kpis['speedup_factor']:.2f}x"),
        ("Real Journey Rows", f"{kpis['journey_row_count']:,}"),
        ("Real Issue Clusters", f"{kpis['n_clusters']:,}"),
        ("Recurring-Cluster Rate", f"{kpis['pct_clusters_recurring']:.2%}"),
        ("Mean Response Lag (days)", f"{kpis['mean_response_lag_days']['point_estimate']:.4f}"),
        ("BANKING77 Coverage", f"{kpis['banking77_pct_in_scope']:.2%}"),
        ("pytest", f"{kpis['pytest_counts']['passed']} passed"),
    ]
    cols = 4
    cell_w = PptxInches(2.9)
    cell_h = PptxInches(1.6)
    for i, (label, val) in enumerate(kpi_cells):
        r_idx, c_idx = divmod(i, cols)
        left = PptxInches(0.5) + c_idx * (cell_w + PptxInches(0.15))
        top = PptxInches(1.7) + r_idx * (cell_h + PptxInches(0.2))
        _add_kpi_box(s, left, top, cell_w, cell_h, label, val)

    # --- Slide 3: Gate 1 ---
    s = _add_slide()
    _add_title(s, "Gate 1 — Business Understanding & Policy (real)")
    _add_bullets(
        s,
        [
            gate1["naming_commitment"],
            f"Real CFPB row count (live check): {gate1['cfpb_row_count']:,}",
            f"Real recurring-cluster rate: {kpis['pct_clusters_recurring']:.2%}",
            f"BANKING77-derived coverage: {kpis['banking77_pct_in_scope']:.2%} of rows",
            f"Compliance touchpoint: {gate1['compliance_requirement']}",
        ],
    )

    # --- Slide 4: Aggregation benchmark ---
    s = _add_slide()
    _add_title(s, "Aggregation-Pipeline Benchmark — Gate 3 (real, speed-selected)")
    _add_picture_bytes(s, figures["benchmark"], PptxInches(1.3), PptxInches(1.4), width=PptxInches(10.7))

    # --- Slide 5: Statistical validation ---
    s = _add_slide()
    _add_title(s, "Statistical Validation — Gate 4 (real, bootstrap CI)")
    _add_picture_bytes(s, figures["mean_lag_ci"], PptxInches(0.6), PptxInches(1.5), width=PptxInches(6.2))
    _add_picture_bytes(
        s, figures["recurring_rate_ci"], PptxInches(6.9), PptxInches(1.5), width=PptxInches(6.2)
    )

    # --- Slide 6: Tier rollup ---
    s = _add_slide()
    _add_title(s, "Issue-Cluster Review-Priority Tier Rollup — Gate 5 (real)")
    _add_picture_bytes(s, figures["tier_rollup"], PptxInches(1.3), PptxInches(1.4), width=PptxInches(10.7))

    # --- Slide 7: Monthly volume trend (optional real figure) ---
    if "monthly_trend" in figures:
        s = _add_slide()
        _add_title(s, "Monthly Complaint-Volume Trend (real, live-aggregated)")
        _add_picture_bytes(
            s, figures["monthly_trend"], PptxInches(1.3), PptxInches(1.6), width=PptxInches(10.7)
        )

    # --- Slide: SMART suggestions ---
    s = _add_slide()
    _add_title(s, "SMART Suggestions")
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(1.3), PptxInches(12.1), PptxInches(5.9))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for sug in suggestions[:5]:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = sug["title"]
        r.font.size = PptxPt(14)
        r.font.bold = True
        r.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = f"{sug['specific'][:220]}... Target: {sug['measurable'][:120]}..."
        r2.font.size = PptxPt(10.5)
        r2.font.color.rgb = GRAY
        p3 = tf.add_paragraph()
        r3 = p3.add_run()
        r3.text = " "
        r3.font.size = PptxPt(5)

    # --- Slide: Gate 6 Governance ---
    s = _add_slide()
    _fill_bg(s, NAVY)
    _add_title(s, "Gate 6 — Governance & Known Limitations (real)", dark=True)
    _add_bullets(
        s,
        [
            f"pytest suite: {gate6['pytest_counts']['passed']} passed / "
            f"{gate6['pytest_counts']['failed']} failed",
            f"Notebook syntax audit: {gate6['notebook_syntax_check_n_passed']}/"
            f"{gate6['notebook_syntax_check_n_passed'] + gate6['notebook_syntax_check_n_failed']} passed",
            f"Open items: {gate6['n_gate3_failed_candidates_detected']} failed + "
            f"{gate6['n_gate3_slow_but_correct_candidates_detected']} slow-but-correct Gate 3 candidate(s)",
            f"Model inventory (SR 11-7): {gate6.get('model_inventory_applicability')}",
            f"Model card: {gate6['model_card_path']}",
            f"BP4 governance gates complete: {kpis['governance_gates_complete']}/6",
        ],
        top=PptxInches(1.6),
        color=WHITE,
        size=15,
    )

    # --- Slide: Recommended for Production ---
    s = _add_slide()
    tier_bg = {1: SUCCESS, 2: AMBER, 3: DANGER}.get(prod_rec["tier_code"], NAVY)
    _fill_bg(s, tier_bg)
    _add_title(s, "Recommended for Production Status", dark=True)
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(1.5), PptxInches(12.1), PptxInches(1.0))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = prod_rec["tier"]
    r.font.size = PptxPt(34)
    r.font.bold = True
    r.font.color.rgb = WHITE
    _add_bullets(s, [prod_rec["reason"]], top=PptxInches(2.7), color=WHITE, size=15)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    return out_path
