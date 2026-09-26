"""
suite_rollup_helpers.py
========================

Helper module for the "00 Suite Executive Rollup" capstone report.

This is a NEW, ADDITIVE deliverable for the Customer360 Navigator Enterprise
Suite (the 8-BP pipeline). It is not part of the original Master Plan; it was
requested directly by the project owner as a suite-wide capstone that
aggregates BP1-BP7's own already-produced Gate-7 executive rollups plus BP8's
own Gate1/Gate2/Gate3 status into one consolidated report.

Hard invariants this module upholds:

  * READ-ONLY over every BP1-BP8 file it opens. This module never writes,
    modifies, or even opens-for-write any file that belongs to BP1-BP8. It
    only ever reads their already-generated JSON/YAML artifacts (and, for
    BP1/BP2 only, their own rendered dashboard HTML, as a disclosed
    cross-check -- see `cross_check_tier_in_html`). All *writing* this
    module does is confined to the three brand-new locations described in
    the project brief: `src/reporting/suite_rollup_helpers.py` (this file),
    `src/reporting/templates/00_suite_dashboard_template.html`, and the
    suite's own new `notebooks/00_suite_executive_rollup/` /
    `reports/00_suite_executive_rollup/` trees.

  * NEVER re-derives or recomputes a metric that a BP's own Gate 7 (or BP8's
    own Gate 1/2/3) already computed. Every number surfaced here is either
    read verbatim from a BP's own manifest/config, or is a *live sum/count*
    over those already-computed numbers (e.g. "how many BPs are flagged",
    "what is the total pytest-passed count across the BPs we have data
    for"). The disclosed exceptions are `derive_bp1_bp2_tier` (fills a
    documented, real schema gap using only BP1's/BP2's own real Gate 6
    governance flags) and `compute_smart_suggestion` (a fixed, deterministic
    rule table over already-real tier/disparate-impact/governance fields --
    never a fabricated or LLM-generated free-text recommendation; see that
    function's docstring for the exact rule table).

  * NEVER contains a financial-impact or assumption-based-content section.
    Every BP1-BP7 manifest that carries `contains_financial_impact_section`
    / `contains_assumption_based_content` keys already sets both `False`;
    this module asserts that (see `assert_no_financial_or_assumption_content`)
    and the suite's own manifest also declares both `False` for itself.
    Smart Suggestions are rule-based next-step guidance ("complete the
    governance review", "continue monitoring"), never a dollar figure, a
    forecast, or a speculative/illustrative claim.

No network calls, no hardcoded absolute paths, no hardcoded metric values.
Every number in the rendered outputs is read live from disk each time this
module's functions are called.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import matplotlib

matplotlib.use("Agg")  # headless rendering -- this module never opens a GUI window
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

# ---------------------------------------------------------------------------
# Design-system constants
# ---------------------------------------------------------------------------
# Copied VERBATIM from src/reporting/bp7_rollup_helpers.py (the most recent,
# most refined per-BP rollup module in this project), per the project's own
# established design-system convention. Do not re-type these from memory or
# alter them here -- if the palette ever changes, change it in
# bp7_rollup_helpers.py first and re-copy.
PALETTE = {
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
# Additional vibrant accent stops used ONLY for the hero-band gradient and
# card-hover glows (decorative surface color, never used to encode data --
# every data-carrying mark in this file still uses CATEGORICAL_SEQUENCE /
# the reserved status colors below, per the project's chart-color
# convention).
HERO_GRADIENT = ("#1E2761", "#2A3A8C", "#4C6EF5")

CATEGORICAL_SEQUENCE = [
    PALETTE["primary_navy"],
    PALETTE["accent_blue"],
    PALETTE["success_green"],
    PALETTE["warning_amber"],
    PALETTE["danger_red"],
    PALETTE["neutral_gray"],
]

# Status colors are RESERVED (never reused as "series N" for an unrelated
# series) -- green=good, amber=conditional/warning, red=flagged/serious,
# gray=not-applicable/no-check. Used consistently for both the tier badges
# and the disparate-impact badges below.
STATUS_COLOR_GOOD = PALETTE["success_green"]
STATUS_COLOR_WARNING = PALETTE["warning_amber"]
STATUS_COLOR_SERIOUS = PALETTE["danger_red"]
STATUS_COLOR_NEUTRAL = PALETTE["neutral_gray"]

FOUR_FIFTHS_RULE_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Structural constants (schema facts about this project, not derived data)
# ---------------------------------------------------------------------------

N_BPS_TOTAL = 8  # A structural fact about the Master Plan's own BP count, not a metric.

BP_ORDER = ["bp1", "bp2", "bp3", "bp4", "bp5", "bp6", "bp7"]

BP_FOLDER_NAMES = {
    "bp1": "bp1_customer_intent_classification",
    "bp2": "bp2_customer_friction_classification",
    "bp3": "bp3_complaint_escalation_prediction",
    "bp4": "bp4_customer_journey_analytics",
    "bp5": "bp5_root_cause_driver_analytics",
    "bp6": "bp6_genai_resolution_assistant",
    "bp7": "bp7_customer_navigator_decision_engine",
}
BP8_FOLDER_NAME = "bp8_executive_product_analytics"

BP_DISPLAY_NAMES = {
    "bp1": "Customer Intent Classification",
    "bp2": "Customer Friction Classification",
    "bp3": "Complaint Escalation Prediction",
    "bp4": "Customer Journey Analytics",
    "bp5": "Root Cause Driver Analytics",
    "bp6": "GenAI Resolution Assistant",
    "bp7": "Customer Navigator Decision Engine",
    "bp8": "Executive Product Analytics",
}

# BPs whose own executive_rollup_manifest.json is a REAL, CONFIRMED gap: no
# production_recommendation_tier (or equivalently-named) key exists at all.
# For these two (and only these two) BPs, `derive_bp1_bp2_tier` is used
# instead of a direct manifest read.
BPS_REQUIRING_DERIVED_TIER = {"bp1", "bp2"}

# The project does not use one canonical key name for the production-tier
# field across BPs (BP3/BP4 use "recommended_for_production_tier"; BP5/BP6/BP7
# use "production_recommendation_tier"). Check both, in this order, rather
# than assuming either is canonical.
TIER_KEY_CANDIDATES = ("production_recommendation_tier", "recommended_for_production_tier")

# Likewise, the champion-model/pipeline/rule-scheme field name is not
# canonical across BPs. Check all three real spellings seen in this suite.
CHAMPION_KEY_CANDIDATES = ("champion_model", "champion_pipeline", "champion_rule_scheme")

# Population-scale record-count fields actually observed in this suite's real
# manifests (currently only BP7's `n_decision_records`). Kept as a list (not
# a single hardcoded key) so that if a future BP's manifest exposes an
# equivalently-scoped count under a different name, it is picked up without
# code changes elsewhere -- but a field is only ever counted if it is
# genuinely present in that BP's own manifest.
RECORD_COUNT_FIELD_CANDIDATES = (
    "n_decision_records",
    "n_gold_records",
    "n_customer_records_scored",
    "n_rows_scored",
)

# The project does not use one canonical key name for the "where are this
# BP's own already-built outputs" block either -- BP1-BP4's manifests use
# "outputs", BP5-BP7's use "output_paths". Check both, in this order.
OUTPUT_PATHS_KEY_CANDIDATES = ("outputs", "output_paths")


# ---------------------------------------------------------------------------
# Small data holders
# ---------------------------------------------------------------------------


@dataclass
class FileFingerprint:
    path: str
    exists: bool
    md5: Optional[str] = None
    size_bytes: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "exists": self.exists,
            "md5": self.md5,
            "size_bytes": self.size_bytes,
        }


@dataclass
class BpRecord:
    """Normalized view of one BP1-BP7's already-real, already-summarized
    executive rollup, plus the two derived-tier inputs for BP1/BP2."""

    bp_key: str
    bp_name: str
    manifest_path: str
    manifest: dict = field(default_factory=dict)
    champion: Optional[Any] = None
    champion_field: Optional[str] = None
    tier: Optional[str] = None
    tier_source: str = "unknown"  # "direct" | "derived"
    tier_code: Optional[int] = None
    generated_at_utc: Optional[str] = None
    contains_financial_impact_section: Optional[bool] = None
    contains_assumption_based_content: Optional[bool] = None
    disparate_impact_status: str = "unknown"
    record_count: Optional[int] = None
    record_count_field: Optional[str] = None
    dashboard_relative_link: Optional[str] = None
    smart_suggestion: str = ""


# ---------------------------------------------------------------------------
# Project-root resolution
# ---------------------------------------------------------------------------
# This module does NOT resolve the project root itself at import time -- the
# notebook's own Section 1 (mirroring every other gate notebook's identical
# bootstrap copy of this same logic) does that before src/ is even on
# sys.path, and passes the already-resolved `project_root` into every
# function in this module. `resolve_project_root` below is kept only as a
# convenience for any OTHER caller of this module (e.g. a test or a future
# notebook) that wants the identical resolution logic without duplicating it
# -- it is a byte-for-byte port of src/utils/performance_setup.py's own real
# `resolve_project_root()` (marker file PROJECT_STRUCTURE_LOCKED.md; env
# override, then bounded upward walk, then bounded downward search), never
# the "configs/+src/ subdirectory" heuristic an earlier draft of this module
# used -- that heuristic is NOT what the rest of this project actually uses,
# and was corrected here after independent verification against the real,
# already-delivered performance_setup.py and BP8 Gate 3's own notebook.

import os  # noqa: E402


def resolve_project_root(
    start_path: Optional[Path] = None,
    marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md",
) -> Path:
    """Resolve the Customer360 project root (see module note above for why
    this mirrors `performance_setup.resolve_project_root()` verbatim).

    1. `C360_PROJECT_ROOT` environment variable, if set, wins outright
       (raises if the marker file isn't there -- never silently falls
       through a misconfigured override).
    2. A bounded upward walk (max 8 levels) from `start_path` (defaults to
       `Path.cwd()` if not given).
    3. A bounded downward search (depth <= 3, hidden dirs skipped) from the
       same starting point -- handles a kernel cwd that is a PARENT of the
       project folder rather than inside it.
    4. Raises RuntimeError with actionable guidance -- never silently falls
       back to a guessed path.
    """
    env_override = os.environ.get("C360_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override)
        if (candidate / marker_filename).exists():
            return candidate
        raise RuntimeError(
            f"C360_PROJECT_ROOT is set to {candidate} but {marker_filename} was not "
            "found there. Fix the environment variable rather than removing this check."
        )

    start = Path(start_path).expanduser().resolve() if start_path is not None else Path.cwd()
    current = start
    for _ in range(8):
        if (current / marker_filename).exists():
            return current
        if current.parent == current:
            break
        current = current.parent

    for depth_root, dirnames, filenames in os.walk(start):
        rel_depth = len(Path(depth_root).relative_to(start).parts)
        if rel_depth > 3:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if marker_filename in filenames:
            return Path(depth_root)

    raise RuntimeError(
        f"Could not resolve PROJECT_ROOT by walking up from {start!r} (checked up to "
        "8 levels), nor by searching up to 3 levels below it, looking for "
        f"{marker_filename}. Set C360_PROJECT_ROOT explicitly to override."
    )


# ---------------------------------------------------------------------------
# File fingerprinting (defense-in-depth: prove no mutation occurred)
# ---------------------------------------------------------------------------


def fingerprint_file(path: Path) -> FileFingerprint:
    """MD5 + size fingerprint of one file. Read-only; never writes."""
    path = Path(path)
    if not path.exists():
        return FileFingerprint(path=str(path), exists=False)
    data = path.read_bytes()
    return FileFingerprint(
        path=str(path),
        exists=True,
        md5=hashlib.md5(
            data, usedforsecurity=False
        ).hexdigest(),  # nosec B324 - content fingerprint, not security
        size_bytes=len(data),
    )


def fingerprint_paths(paths: list[Path]) -> dict[str, dict]:
    """Fingerprint several files at once, keyed by string path."""
    return {str(p): fingerprint_file(p).to_dict() for p in paths}


def assert_no_mutation(before: dict[str, dict], after: dict[str, dict]) -> None:
    """Assert that every path fingerprinted in `before` is byte-for-byte
    identical in `after`. Raises AssertionError naming the first mismatch.

    This is the notebook's structural proof that this suite-level rollup
    never wrote to any BP1-BP8 file it opened.
    """
    for path, before_fp in before.items():
        after_fp = after.get(path)
        assert after_fp is not None, f"Fingerprint missing on re-check for {path}"
        assert before_fp == after_fp, (
            f"MUTATION DETECTED on a BP1-BP8 file this rollup only ever "
            f"should have READ: {path}\n  before={before_fp}\n  after={after_fp}"
        )


# ---------------------------------------------------------------------------
# Low-level, defensive readers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    """Load a JSON file. Returns {} if the file does not exist (callers that
    need to distinguish "absent" from "empty" should check Path.exists()
    themselves before calling this -- see the BP8 Gate 3 handling below)."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_gate6_governance_block(config_path: Path) -> dict:
    """Read the `gate6_governance:` block from a BP's own config YAML.

    Per the project brief, only BP1's and BP2's configs are in this
    deliverable's read scope (they are the only two BPs whose manifest is
    missing a tier field, so they are the only two whose gate6 governance
    flags this module needs). Returns {} if the block or file is absent.
    """
    cfg = load_yaml(config_path)
    return cfg.get("gate6_governance", {}) or {}


# ---------------------------------------------------------------------------
# BP1/BP2 tier derivation (the ONE place this module derives rather than
# directly reads a value)
# ---------------------------------------------------------------------------


def derive_bp1_bp2_tier(
    gate6_pytest_all_passed: Optional[bool],
    gate6_notebook_syntax_all_passed: Optional[bool],
) -> str:
    """Derive BP1's/BP2's production-recommendation tier.

    WHY THIS FUNCTION EXISTS: BP1's and BP2's own real
    `executive_rollup_manifest.json` files do not carry a
    `production_recommendation_tier` (or `recommended_for_production_tier`)
    key at all. This is a confirmed, real schema gap -- BP1 and BP2 predate
    that field being added to the manifest schema -- not a bug to silently
    paper over or an invitation to fabricate a plausible-looking value.

    Rather than inventing a number, this function applies the same real,
    already-documented reasoning that BP1's and BP2's own rendered dashboards
    state in prose: Tier 2 ("CONDITIONAL - GOVERNANCE REVIEW REQUIRED") is
    structurally UNREACHABLE for BP1 and BP2, because their own Gate1-6
    artifacts carry no ECOA/Reg B disparate-impact check at all (that check
    was only introduced starting with BP3). With Tier 2 structurally
    unreachable, only two real outcomes remain for BP1/BP2 -- never three --
    and Gate 6's own governance status (pytest + notebook-syntax checks, read
    live from each BP's own config YAML `gate6_governance:` block) is exactly
    what those BPs' own real dashboards use to distinguish between them:

      * both `pytest_all_passed` and `notebook_syntax_all_passed` True
        -> "RECOMMENDED FOR PRODUCTION"
      * anything else
        -> "NOT RECOMMENDED FOR PRODUCTION - governance checks failed"

    This function performs no I/O; it is a pure function of its two boolean
    inputs, which callers must read live from each BP's own real config.
    """
    if gate6_pytest_all_passed is True and gate6_notebook_syntax_all_passed is True:
        return "RECOMMENDED FOR PRODUCTION"
    return "NOT RECOMMENDED FOR PRODUCTION - governance checks failed"


def cross_check_tier_in_html(html_path: Path, tier_string: str, bp_label: str) -> None:
    """Defense-in-depth cross-check (never the primary source): assert that
    the derived tier string literally appears in BP1's/BP2's own rendered
    dashboard HTML. Mirrors this project's own established pattern of
    catching bugs via independent structural re-verification.

    This function only READS the HTML file. Raises AssertionError naming the
    BP and both strings if the substring is not found.
    """
    html_path = Path(html_path)
    if not html_path.exists():
        raise AssertionError(
            f"Cross-check failed for {bp_label}: dashboard HTML not found at " f"{html_path}"
        )
    text = html_path.read_text(encoding="utf-8")
    assert tier_string in text, (
        f"Cross-check failed for {bp_label}: derived tier string "
        f"{tier_string!r} was not found as a substring of {html_path}"
    )


# ---------------------------------------------------------------------------
# Per-BP field extraction (defensive: dict.get(), never dict[...])
# ---------------------------------------------------------------------------


def extract_champion(manifest: dict) -> tuple[Optional[Any], Optional[str]]:
    """Return (value, field_name_used) for whichever champion-* key is
    actually present in this BP's manifest. Different BPs use different
    real key names (champion_model / champion_pipeline / champion_rule_scheme)
    -- never assume one canonical name."""
    for key in CHAMPION_KEY_CANDIDATES:
        if key in manifest:
            return manifest[key], key
    return None, None


def extract_tier_direct(manifest: dict) -> tuple[Optional[str], Optional[int]]:
    """Return (tier_string, tier_code) read directly from the manifest, or
    (None, None) if neither known tier key is present (the BP1/BP2 gap)."""
    for key in TIER_KEY_CANDIDATES:
        if key in manifest:
            return manifest[key], manifest.get("production_recommendation_tier_code")
    return None, None


def classify_disparate_impact(manifest: dict) -> str:
    """Classify a BP's disparate-impact status into one of four buckets,
    read defensively from whichever real field this BP's manifest exposes:

      * "flagged"               -- a real boolean flag is present and True
                                    (BP3's disparate_impact_flagged,
                                     BP7's flagged_four_fifths_rule)
      * "not_flagged"            -- that same flag is present and False
      * "not_applicable"         -- ecoa_reg_b_disparate_impact_applicability
                                    == "NOT_APPLICABLE" (BP4/BP5/BP6)
      * "structurally_no_check"  -- neither field is present at all
                                    (BP1/BP2's real, documented gap: no
                                    ECOA/Reg B check exists pre-BP3)

    "not_applicable" and "structurally_no_check" are kept as SEPARATE
    buckets, never folded into "not_flagged", per the project brief.
    """
    for key in ("disparate_impact_flagged", "flagged_four_fifths_rule"):
        if key in manifest:
            return "flagged" if manifest[key] else "not_flagged"
    applicability = manifest.get("ecoa_reg_b_disparate_impact_applicability")
    if applicability == "NOT_APPLICABLE":
        return "not_applicable"
    return "structurally_no_check"


def extract_record_count(manifest: dict) -> tuple[Optional[int], Optional[str]]:
    """Return (count, field_name_used) for whichever population-scale
    record-count field is actually present in this BP's manifest, or
    (None, None) if none of the known candidate fields are present."""
    for key in RECORD_COUNT_FIELD_CANDIDATES:
        if key in manifest:
            return manifest[key], key
    return None, None


def extract_output_paths(manifest: dict) -> dict:
    """Return the {"dashboard_html": ..., "report_docx": ..., ...} dict for
    whichever real key name this BP's manifest uses ("outputs" for
    BP1-BP4, "output_paths" for BP5-BP7), or {} if neither is present."""
    for key in OUTPUT_PATHS_KEY_CANDIDATES:
        if key in manifest and isinstance(manifest[key], dict):
            return manifest[key]
    return {}


def compute_dashboard_relative_link(manifest: dict) -> Optional[str]:
    """Compute a relative-from-`reports/00_suite_executive_rollup/` hyperlink
    to this BP's own already-built, already-real dashboard HTML, using ONLY
    the path that BP's own manifest already states for itself (never a
    constructed/guessed filename). Returns None if the manifest exposes no
    dashboard_html output path.

    The suite dashboard lives at reports/00_suite_executive_rollup/<file>.html
    and every BP's own dashboard lives at reports/<bp_folder>/executive_rollup/
    <file>.html -- both are direct children of reports/, so the relative link
    is always "../" once, then the BP's own path with the leading "reports"
    path segment (in whichever separator style that BP's manifest used)
    stripped off.
    """
    outputs = extract_output_paths(manifest)
    raw = outputs.get("dashboard_html")
    if not raw:
        return None
    normalized = str(raw).replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    if parts and parts[0].lower() == "reports":
        parts = parts[1:]
    return "../" + "/".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Smart Suggestions -- deterministic, rule-based next-step guidance
# ---------------------------------------------------------------------------
# These are NOT AI-generated free text and NOT assumption-based/illustrative
# content. Each suggestion is the output of a fixed if/elif rule table over
# fields this module has already read live from a BP's own real manifest /
# governance block -- the identical pattern already established by
# `derive_bp1_bp2_tier` above. No dollar figure, forecast, or speculative
# claim ever appears in a Smart Suggestion.


def compute_smart_suggestion(bp_key: str, tier: Optional[str], disparate_impact_status: str) -> str:
    """Deterministic recommended-next-step text for one BP1-BP7, derived
    only from that BP's own already-loaded real `tier` and
    `disparate_impact_status`. Rule table (checked in this fixed order):

      1. tier contains "NOT RECOMMENDED"
         -> recommend fixing the named governance failure first.
      2. tier contains "CONDITIONAL"
         -> recommend completing the named governance review before
            production use.
      3. disparate_impact_status == "flagged"
         -> recommend continued disparate-impact monitoring alongside
            production use.
      4. tier contains "RECOMMENDED FOR PRODUCTION" (unqualified, and not
         flagged) -> recommend routine re-validation at the next scheduled
         run; no other action required.
      5. tier contains "RECOMMENDED" but is qualified (e.g. BP5's real
         "Recommended for Decision-Support Use, With Monitoring") -> recommend
         continuing under the BP's own stated qualification/monitoring
         condition, using that BP's own literal tier text rather than
         collapsing it to an unqualified "production-ready" claim.
      6. anything else (tier missing/unrecognized)
         -> recommend confirming this BP's own Gate 7 rollup before relying
            on its status here.
    """
    tier_text = (tier or "").upper()

    if "NOT RECOMMENDED" in tier_text:
        return (
            "Resolve the governance-check failure noted in this BP's own Gate 6 "
            "block before any production use; re-run Gate 6 once fixed."
        )
    if "CONDITIONAL" in tier_text:
        return (
            "Complete the governance review this BP's own Gate 7 rollup calls for "
            "before moving to production; re-check after review."
        )
    if disparate_impact_status == "flagged":
        return (
            "Keep the disparate-impact monitoring signal active in production; "
            "route continued findings to a human compliance reviewer each run."
        )
    if tier_text == "RECOMMENDED FOR PRODUCTION":
        return (
            "No blocking action. Re-validate at the next scheduled re-run, "
            "consistent with this suite's standing monitoring cadence."
        )
    if "RECOMMENDED" in tier_text:
        return (
            f'Proceed under this BP\'s own stated qualification -- "{tier}" -- '
            "rather than treating it as an unconditional production-ready result; "
            "keep the monitoring it calls for active."
        )
    return "Confirm this BP's own Gate 7 rollup directly; its tier field was not recognized here."


def compute_bp8_smart_suggestion(bp8: dict) -> str:
    """Deterministic recommended-next-step text for BP8, derived only from
    its own already-loaded real gate1_confirmed / gate2_confirmed /
    gate3_status fields (same rule-table pattern as `compute_smart_suggestion`,
    BP8-specific because it has no production-recommendation-tier concept)."""
    if not bp8.get("gate1_confirmed"):
        return "Run BP8 Gate 1 (aggregation scope) before Gate 2/3 can be considered complete."
    if not bp8.get("gate2_confirmed"):
        return "Run BP8 Gate 2 (Gold-table build) to complete the base Power BI semantic layer."
    if bp8.get("gate3_status") != "real-run confirmed":
        return (
            "Gate 3 (decision-engine KPI extension) is delivered as source but not yet "
            "real-run -- run it, then re-run this suite rollup to pick up the confirmation."
        )
    return (
        "All 3 of BP8's real gates are confirmed. Remaining step is the human, "
        "Power BI Desktop (.pbix) build over these Gold tables (Master Plan Section 19)."
    )


# ---------------------------------------------------------------------------
# Top-level loader: BP1-BP7
# ---------------------------------------------------------------------------


def load_bp_record(
    project_root: Path,
    bp_key: str,
    gate6_blocks: dict[str, dict],
) -> BpRecord:
    """Load and normalize one BP1-BP7's own executive_rollup_manifest.json.

    `gate6_blocks` is the dict of already-loaded gate6_governance blocks
    (currently only populated for bp1/bp2, per this deliverable's strict
    read-only file list -- see `load_all_bp_summaries`).
    """
    folder = BP_FOLDER_NAMES[bp_key]
    manifest_path = project_root / "notebooks" / folder / "artifacts" / "executive_rollup_manifest.json"
    manifest = load_json(manifest_path)

    champion, champion_field = extract_champion(manifest)
    tier_direct, tier_code = extract_tier_direct(manifest)

    if tier_direct is not None:
        tier, tier_source = tier_direct, "direct"
    elif bp_key in BPS_REQUIRING_DERIVED_TIER:
        gate6 = gate6_blocks.get(bp_key, {})
        tier = derive_bp1_bp2_tier(
            gate6.get("pytest_all_passed"),
            gate6.get("notebook_syntax_all_passed"),
        )
        tier_source = "derived"
    else:
        # A BP other than bp1/bp2 with no tier field would be a genuine
        # schema surprise this deliverable is not authorized to paper over.
        raise KeyError(
            f"{bp_key}: no tier field found in {manifest_path} and no "
            "derivation rule is defined for this BP (only bp1/bp2 have one)."
        )

    record_count, record_count_field = extract_record_count(manifest)
    disparate_impact_status = classify_disparate_impact(manifest)

    return BpRecord(
        bp_key=bp_key,
        bp_name=BP_DISPLAY_NAMES[bp_key],
        manifest_path=str(manifest_path),
        manifest=manifest,
        champion=champion,
        champion_field=champion_field,
        tier=tier,
        tier_source=tier_source,
        tier_code=tier_code,
        generated_at_utc=manifest.get("generated_at_utc"),
        contains_financial_impact_section=manifest.get("contains_financial_impact_section"),
        contains_assumption_based_content=manifest.get("contains_assumption_based_content"),
        disparate_impact_status=disparate_impact_status,
        record_count=record_count,
        record_count_field=record_count_field,
        dashboard_relative_link=compute_dashboard_relative_link(manifest),
        smart_suggestion=compute_smart_suggestion(bp_key, tier, disparate_impact_status),
    )


# ---------------------------------------------------------------------------
# BP8 loader
# ---------------------------------------------------------------------------


def load_bp8_summary(project_root: Path) -> dict:
    """Load BP8's own Gate1 (policy.json), Gate2 (gold table manifest), and
    Gate3 (KPI manifest, which may not exist yet) artifacts.

    BP8 is structurally different from BP1-BP7: it has no
    production_recommendation_tier concept (it is a Gold-table / Power BI
    aggregation layer, never a modeling problem), so this function returns a
    differently-shaped dict rather than a BpRecord.
    """
    folder = BP8_FOLDER_NAME
    bp8_dir = project_root / "notebooks" / folder / "artifacts"

    gate1_path = bp8_dir / "policy.json"
    gate2_path = bp8_dir / "gate2_gold_table_manifest.json"
    gate3_path = bp8_dir / "gate3_decision_engine_kpi_manifest.json"

    gate1 = load_json(gate1_path)
    gate2 = load_json(gate2_path)

    gate3_exists = gate3_path.exists()
    gate3 = load_json(gate3_path) if gate3_exists else {}

    config_path = project_root / "configs" / "bp8_executive_product_analytics.yaml"
    config = load_yaml(config_path)

    result = {
        "bp_key": "bp8",
        "bp_name": BP_DISPLAY_NAMES["bp8"],
        "gate1_path": str(gate1_path),
        "gate1": gate1,
        "gate1_generated_at_utc": gate1.get("generated_at_utc"),
        "gate1_confirmed": bool(gate1.get("generated_at_utc")),
        "aggregation_scope_definition": gate1.get("aggregation_scope_definition"),
        "scope_boundaries": gate1.get("scope_boundaries"),
        "explicitly_out_of_scope": gate1.get("explicitly_out_of_scope"),
        "gate2_path": str(gate2_path),
        "gate2": gate2,
        "gate2_generated_at_utc": gate2.get("generated_at_utc"),
        "gate2_confirmed": bool(gate2.get("generated_at_utc")),
        # gate2's own manifest never wrote "n_kpi_categories_ready" / "n_kpi_categories_deferred" /
        # "gold_tables_written_count" as scalar fields - only the real underlying
        # "kpi_category_scope" dict and "gold_tables_written" list exist. Reading the absent scalar
        # keys silently returned None -> rendered as the literal string "None"/"0" on the suite
        # dashboard even though the real data one field over was fully populated. Compute these
        # three counts directly from that real data instead of trusting a field that was never
        # written. (Falls back to an explicit field if a future gate2 run starts writing one.)
        "n_kpi_categories_ready": gate2.get("n_kpi_categories_ready", sum(
            1 for v in gate2.get("kpi_category_scope", {}).values() if v.get("ready")
        )),
        "n_kpi_categories_deferred": gate2.get("n_kpi_categories_deferred", sum(
            1 for v in gate2.get("kpi_category_scope", {}).values() if not v.get("ready")
        )),
        "gold_tables_written_count": gate2.get(
            "gold_tables_written_count", len(gate2.get("gold_tables_written", gate2.get("gold_tables", [])))
        ),
        "gold_tables": gate2.get("gold_tables_written", gate2.get("gold_tables", [])),
        "gate3_manifest_path": str(gate3_path),
        "gate3_exists": gate3_exists,
        "gate3": gate3,
        "gate3_status": (
            "delivered as source, not yet real-run" if not gate3_exists else "real-run confirmed"
        ),
        "gate3_generated_at_utc": gate3.get("generated_at_utc") if gate3_exists else None,
        "gate3_n_kpi_tables_ready": gate3.get("n_kpi_tables_ready") if gate3_exists else None,
        "gate3_gold_tables": gate3.get("gold_tables_written", []) if gate3_exists else [],
        "config_status": config.get("status"),
        "config_has_gate3_block": "gate3_decision_engine_kpi" in config
        or any(str(k).lower().startswith("gate3") for k in config.keys()),
    }
    result["smart_suggestion"] = compute_bp8_smart_suggestion(result)
    return result


# ---------------------------------------------------------------------------
# Top-level bundle loader
# ---------------------------------------------------------------------------


def load_all_bp_summaries(project_root: Path) -> dict:
    """Load BP1-BP7's executive rollup manifests and BP8's Gate1/2/3 status
    into one bundle dict. This is the single entry point the notebook calls.

    Returns a dict with:
      - "bp1".."bp7": BpRecord instances
      - "bp8": dict from `load_bp8_summary`
      - "_gate6_blocks": {"bp1": {...}, "bp2": {...}} -- the raw gate6
        governance blocks read from bp1/bp2's own config YAML (the only two
        BP configs this deliverable is authorized to read), kept around so
        `compute_suite_kpis` can sum pytest-passed counts without
        re-reading the files.
    """
    project_root = Path(project_root)

    gate6_blocks = {
        "bp1": load_gate6_governance_block(
            project_root / "configs" / "bp1_customer_intent_classification.yaml"
        ),
        "bp2": load_gate6_governance_block(
            project_root / "configs" / "bp2_customer_friction_classification.yaml"
        ),
    }

    bundle: dict = {"_gate6_blocks": gate6_blocks}
    for bp_key in BP_ORDER:
        bundle[bp_key] = load_bp_record(project_root, bp_key, gate6_blocks)

    bundle["bp8"] = load_bp8_summary(project_root)

    return bundle


# ---------------------------------------------------------------------------
# Suite-level KPIs
# ---------------------------------------------------------------------------


def compute_suite_kpis(bundle: dict) -> dict:
    """Compute suite-wide KPIs. Every number here is a live sum/count over
    the already-loaded per-BP data in `bundle` -- nothing is precomputed or
    hardcoded, and nothing here re-derives a number any BP's own Gate 7 (or
    BP8's own Gate 1/2/3) already computed.
    """
    bp_records: list[BpRecord] = [bundle[k] for k in BP_ORDER if k in bundle]

    n_bps_fully_complete_gate7 = sum(1 for r in bp_records if r.generated_at_utc)

    tier_counts: dict[str, int] = {}
    for r in bp_records:
        tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1

    n_bps_recommended_for_production = sum(
        1 for r in bp_records if "RECOMMENDED FOR PRODUCTION" in (r.tier or "").upper()
    )

    disparate_impact_counts = {
        "flagged": 0,
        "not_flagged": 0,
        "not_applicable": 0,
        "structurally_no_check": 0,
    }
    for r in bp_records:
        disparate_impact_counts[r.disparate_impact_status] = (
            disparate_impact_counts.get(r.disparate_impact_status, 0) + 1
        )
    n_bps_disparate_impact_flagged = disparate_impact_counts["flagged"]

    # pytest-passed sum: only over BPs whose gate6_governance block this
    # deliverable actually has (bp1/bp2, per the strict read-only file list
    # -- BP3-BP7's own configs are out of this deliverable's read scope).
    gate6_blocks = bundle.get("_gate6_blocks", {})
    pytest_passed_total = 0
    pytest_contributing_bps: list[str] = []
    for bp_key, block in gate6_blocks.items():
        val = block.get("pytest_passed")
        if val is not None:
            pytest_passed_total += val
            pytest_contributing_bps.append(bp_key)

    # population-scale record-count sum: only over BPs whose manifest
    # actually exposes one of RECORD_COUNT_FIELD_CANDIDATES.
    record_total = 0
    record_contributing_bps: list[str] = []
    for r in bp_records:
        if r.record_count is not None:
            record_total += r.record_count
            record_contributing_bps.append(r.bp_key)

    financial_assumption_audit = {
        r.bp_key: {
            "contains_financial_impact_section": r.contains_financial_impact_section,
            "contains_assumption_based_content": r.contains_assumption_based_content,
        }
        for r in bp_records
    }

    bp8 = bundle.get("bp8", {})

    return {
        "n_bps_total": N_BPS_TOTAL,
        "n_bps_fully_complete_gate7": n_bps_fully_complete_gate7,
        "n_bps_recommended_for_production": n_bps_recommended_for_production,
        "tier_counts": tier_counts,
        "disparate_impact_counts": disparate_impact_counts,
        "n_bps_disparate_impact_flagged": n_bps_disparate_impact_flagged,
        "total_pytest_passed_across_suite": pytest_passed_total,
        "pytest_passed_contributing_bps": pytest_contributing_bps,
        "n_pytest_passed_contributing_bps": len(pytest_contributing_bps),
        "total_decision_or_gold_records_across_suite": record_total,
        "record_count_contributing_bps": record_contributing_bps,
        "n_record_count_contributing_bps": len(record_contributing_bps),
        "financial_assumption_audit": financial_assumption_audit,
        "bp8_gate1_confirmed": bp8.get("gate1_confirmed"),
        "bp8_gate2_confirmed": bp8.get("gate2_confirmed"),
        "bp8_n_kpi_categories_ready": bp8.get("n_kpi_categories_ready"),
        "bp8_n_kpi_categories_deferred": bp8.get("n_kpi_categories_deferred"),
        "bp8_gold_tables_written_count": bp8.get("gold_tables_written_count"),
        "bp8_gate3_status": bp8.get("gate3_status"),
        "bp8_gate3_n_kpi_tables_ready": bp8.get("gate3_n_kpi_tables_ready"),
    }


def assert_no_financial_or_assumption_content(bundle: dict) -> None:
    """Assert every BP1-BP7 manifest that carries the two banned-content
    flags has both set to False. Financial-impact / assumption-based content
    is permanently banned project-wide; this is the structural check."""
    for bp_key in BP_ORDER:
        r: BpRecord = bundle[bp_key]
        if r.contains_financial_impact_section is not None:
            assert r.contains_financial_impact_section is False, (
                f"{bp_key}: contains_financial_impact_section is not False "
                f"({r.contains_financial_impact_section!r}) -- this is a "
                "project-wide banned-content violation."
            )
        if r.contains_assumption_based_content is not None:
            assert r.contains_assumption_based_content is False, (
                f"{bp_key}: contains_assumption_based_content is not False "
                f"({r.contains_assumption_based_content!r}) -- this is a "
                "project-wide banned-content violation."
            )


# ---------------------------------------------------------------------------
# Status DataFrame
# ---------------------------------------------------------------------------


def build_status_dataframe(bundle: dict) -> pd.DataFrame:
    """Build a per-BP status table (BP1-BP7) as a pandas DataFrame."""
    rows = []
    for bp_key in BP_ORDER:
        r: BpRecord = bundle[bp_key]
        rows.append(
            {
                "bp": bp_key.upper(),
                "bp_name": r.bp_name,
                "champion": r.champion,
                "champion_field": r.champion_field,
                "tier": r.tier,
                "tier_source": r.tier_source,
                "tier_code": r.tier_code,
                "disparate_impact_status": r.disparate_impact_status,
                "generated_at_utc": r.generated_at_utc,
                "record_count": r.record_count,
                "record_count_field": r.record_count_field,
                "smart_suggestion": r.smart_suggestion,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Charts (mirrors the fig_* function style used in bp7_rollup_helpers.py)
# ---------------------------------------------------------------------------
# These matplotlib PNG renders are kept for the PPTX deck (which embeds a
# raster image, not an interactive element) and as a static/print/accessible
# fallback inside the HTML dashboard's collapsible "Table & static-chart
# view" section (dataviz-skill accessibility requirement: a non-interactive
# table/print view must exist alongside any interactive chart). The HTML
# dashboard's PRIMARY charts are drawn client-side as interactive inline SVG
# from the embedded JSON payload -- see `build_suite_chart_payload` and the
# template's own <script> block.


def fig_tier_distribution(df: pd.DataFrame):
    """Bar chart of production-recommendation-tier distribution across BP1-7."""
    counts = df["tier"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)] for i in range(len(counts))]
    ax.bar(range(len(counts)), counts.values, color=colors)
    ax.set_xticks(range(len(counts)))
    ax.set_xticklabels([_wrap_label(t) for t in counts.index], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Number of BPs", color=PALETTE["ink"])
    ax.set_title("Production-Recommendation Tier Distribution (BP1-BP7)", color=PALETTE["ink"])
    ax.set_facecolor(PALETTE["surface_light"])
    fig.patch.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def fig_pytest_passed_per_bp(bundle: dict):
    """Bar chart of pytest-passed counts per BP, over only the BPs whose
    gate6_governance block this deliverable actually read (bp1/bp2)."""
    gate6_blocks = bundle.get("_gate6_blocks", {})
    bp_keys = [k for k in BP_ORDER if k in gate6_blocks and gate6_blocks[k].get("pytest_passed") is not None]
    values = [gate6_blocks[k]["pytest_passed"] for k in bp_keys]

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)] for i in range(len(bp_keys))]
    ax.bar([k.upper() for k in bp_keys], values, color=colors)
    ax.set_ylabel("pytest tests passed", color=PALETTE["ink"])
    ax.set_title(
        "Gate 6 pytest-passed count per BP\n(only BPs whose config this rollup reads)",
        color=PALETTE["ink"],
        fontsize=10,
    )
    ax.set_facecolor(PALETTE["surface_light"])
    fig.patch.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def _wrap_label(text: str, width: int = 18) -> str:
    words = str(text).split()
    lines, current = [], ""
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = w
        else:
            current = (current + " " + w).strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


def fig_to_png_bytes(fig) -> bytes:
    """Render a matplotlib figure to raw PNG bytes and close it. Callers
    that need both the HTML (base64) and PPTX (raw bytes) embedding should
    call this once and derive both from the returned bytes, rather than
    rendering the same figure twice."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def png_bytes_to_base64(png_bytes: bytes) -> str:
    """Base64-encode raw PNG bytes, for embedding in the HTML dashboard as
    a data: URI (no on-disk image file needed)."""
    import base64

    return base64.b64encode(png_bytes).decode("ascii")


# ---------------------------------------------------------------------------
# Story captions -- 2-line, auto-composed from real already-computed numbers
# ---------------------------------------------------------------------------
# Every caption below is an f-string over values already present in `kpis`/
# `bundle` (the same objects `compute_suite_kpis` / `load_all_bp_summaries`
# already built from real, live-read data) -- never a hardcoded sentence
# with numbers dropped in, and never a claim not directly backed by one of
# those fields.


def story_tier(kpis: dict) -> str:
    n_rec = kpis["n_bps_recommended_for_production"]
    n_total = kpis["n_bps_fully_complete_gate7"]
    flagged = kpis["n_bps_disparate_impact_flagged"]
    line1 = f"{n_rec} of {n_total} completed BPs carry a RECOMMENDED FOR PRODUCTION tier."
    line2 = (
        f"{flagged} BP(s) hold an open disparate-impact flag for continued monitoring."
        if flagged
        else "None of the 7 BPs are currently flagged for disparate impact."
    )
    return f"{line1}\n{line2}"


def story_disparate_impact(kpis: dict) -> str:
    c = kpis["disparate_impact_counts"]
    line1 = (
        f"{c['flagged']} flagged, {c['not_flagged']} checked-and-clear, "
        f"{c['not_applicable']} not applicable, {c['structurally_no_check']} pre-date the check."
    )
    line2 = "The ECOA/Reg B check was introduced starting with BP3; BP1/BP2 pre-date it structurally."
    return f"{line1}\n{line2}"


def story_records(kpis: dict) -> str:
    total = kpis["total_decision_or_gold_records_across_suite"]
    n_contrib = kpis["n_record_count_contributing_bps"]
    contrib_bps = ", ".join(b.upper() for b in kpis["record_count_contributing_bps"]) or "none"
    line1 = f"{total:,} records represented across {n_contrib} BP(s) exposing a population-scale count."
    line2 = f"Contributing BP(s): {contrib_bps}."
    return f"{line1}\n{line2}"


def story_pytest(kpis: dict) -> str:
    total = kpis["total_pytest_passed_across_suite"]
    n_contrib = kpis["n_pytest_passed_contributing_bps"]
    line1 = f"{total} pytest cases passed across {n_contrib} BP(s) whose Gate 6 config this rollup reads."
    line2 = "Only BP1/BP2 configs are in this deliverable's disclosed read scope for this count."
    return f"{line1}\n{line2}"


def story_bp8(bp8: dict) -> str:
    tables = bp8.get("gold_tables_written_count") or 0
    status = bp8.get("gate3_status", "unknown")
    line1 = f"{tables} Gold tables written at Gate 2; Gate 3 (decision-engine KPIs) is {status}."
    line2 = "The suite's own Power BI (.pbix) build is a human step (Master Plan Section 19)."
    return f"{line1}\n{line2}"


def story_generated_dates(bundle: dict) -> str:
    dated = [(k, bundle[k].generated_at_utc) for k in BP_ORDER if bundle[k].generated_at_utc]
    line1 = f"{len(dated)} of 7 BPs carry a real Gate 7 generation timestamp."
    if dated:
        latest_bp, latest_ts = max(dated, key=lambda t: t[1])
        line2 = f"Most recently generated: {latest_bp.upper()} at {latest_ts}."
    else:
        line2 = "No Gate 7 generation timestamps found."
    return f"{line1}\n{line2}"


# ---------------------------------------------------------------------------
# Chart data payload -- embedded as JSON for the template's client-side
# interactive SVG charts, filters, and animated counters
# ---------------------------------------------------------------------------


def build_suite_chart_payload(bundle: dict, kpis: dict, df: pd.DataFrame) -> dict:
    """Assemble one JSON-serializable dict containing every value the
    template's client-side JavaScript needs to draw its interactive charts,
    drive its filter controls, and animate its KPI counters. Every value
    here is read straight out of `bundle`/`kpis`/`df`, which were already
    built entirely from real, live-read BP1-BP8 data -- this function adds
    no new data source and performs no re-derivation of its own beyond
    plain reshaping (e.g. dict-of-counts -> list-of-{label,value} for the
    chart-drawing JS to iterate over)."""
    tier_series = [{"label": tier, "value": count} for tier, count in kpis["tier_counts"].items()]
    di_labels = {
        "flagged": "Flagged",
        "not_flagged": "Checked, Not Flagged",
        "not_applicable": "Not Applicable",
        "structurally_no_check": "Pre-dates the Check",
    }
    di_series = [
        {"label": di_labels[k], "value": kpis["disparate_impact_counts"][k], "key": k}
        for k in ("flagged", "not_flagged", "not_applicable", "structurally_no_check")
    ]
    records_series = [
        {"label": bp_key.upper(), "value": bundle[bp_key].record_count}
        for bp_key in BP_ORDER
        if bundle[bp_key].record_count is not None
    ]
    gate6_blocks = bundle.get("_gate6_blocks", {})
    pytest_series = [
        {"label": k.upper(), "value": gate6_blocks[k]["pytest_passed"]}
        for k in BP_ORDER
        if k in gate6_blocks and gate6_blocks[k].get("pytest_passed") is not None
    ]
    timeline_series = [
        {"label": bp_key.upper(), "value": bundle[bp_key].generated_at_utc}
        for bp_key in BP_ORDER
        if bundle[bp_key].generated_at_utc
    ]
    bp8 = bundle.get("bp8", {})
    bp8_gold_series = [
        {"label": t.get("category", t.get("filename", "?")), "value": t.get("n_rows")}
        for t in (bp8.get("gold_tables") or [])
        if isinstance(t, dict) and t.get("n_rows") is not None
    ]

    cards = []
    for bp_key in BP_ORDER:
        r: BpRecord = bundle[bp_key]
        tier_text = (r.tier or "").upper()
        if "NOT RECOMMENDED" in tier_text:
            status_color = STATUS_COLOR_SERIOUS
        elif "CONDITIONAL" in tier_text:
            status_color = STATUS_COLOR_WARNING
        elif tier_text == "RECOMMENDED FOR PRODUCTION":
            status_color = STATUS_COLOR_GOOD
        elif "RECOMMENDED" in tier_text:
            # A qualified recommendation (e.g. BP5's real "Recommended for
            # Decision-Support Use, With Monitoring") -- distinct from an
            # unconditional production-ready tier, so it gets the same
            # reserved "needs continued attention" amber as CONDITIONAL,
            # never collapsed into plain green.
            status_color = STATUS_COLOR_WARNING
        else:
            status_color = STATUS_COLOR_NEUTRAL
        di_color = {
            "flagged": STATUS_COLOR_SERIOUS,
            "not_flagged": STATUS_COLOR_GOOD,
            "not_applicable": STATUS_COLOR_NEUTRAL,
            "structurally_no_check": STATUS_COLOR_NEUTRAL,
        }[r.disparate_impact_status]
        cards.append(
            {
                "bp_key": bp_key.upper(),
                "bp_name": r.bp_name,
                "champion": r.champion,
                "champion_field": r.champion_field,
                "tier": r.tier,
                "tier_source": r.tier_source,
                "status_color": status_color,
                "disparate_impact_status": r.disparate_impact_status,
                "disparate_impact_label": di_labels[r.disparate_impact_status],
                "di_color": di_color,
                "record_count": r.record_count,
                "generated_at_utc": r.generated_at_utc,
                "dashboard_relative_link": r.dashboard_relative_link,
                "smart_suggestion": r.smart_suggestion,
            }
        )

    return {
        "tier_series": tier_series,
        "disparate_impact_series": di_series,
        "records_series": records_series,
        "pytest_series": pytest_series,
        "timeline_series": timeline_series,
        "bp8_gold_series": bp8_gold_series,
        "cards": cards,
        "categorical_sequence": CATEGORICAL_SEQUENCE,
        "kpis": {
            "n_bps_total": kpis["n_bps_total"],
            "n_bps_fully_complete_gate7": kpis["n_bps_fully_complete_gate7"],
            "n_bps_recommended_for_production": kpis["n_bps_recommended_for_production"],
            "n_bps_disparate_impact_flagged": kpis["n_bps_disparate_impact_flagged"],
            "total_pytest_passed_across_suite": kpis["total_pytest_passed_across_suite"],
            "total_decision_or_gold_records_across_suite": kpis[
                "total_decision_or_gold_records_across_suite"
            ],
        },
        "bp8": {
            "gate1_confirmed": bp8.get("gate1_confirmed"),
            "gate2_confirmed": bp8.get("gate2_confirmed"),
            "gate3_status": bp8.get("gate3_status"),
            "gold_tables_written_count": bp8.get("gold_tables_written_count"),
            "n_kpi_categories_ready": bp8.get("n_kpi_categories_ready"),
            "n_kpi_categories_deferred": bp8.get("n_kpi_categories_deferred"),
            "smart_suggestion": bp8.get("smart_suggestion"),
        },
    }


# ---------------------------------------------------------------------------
# HTML dashboard rendering
# ---------------------------------------------------------------------------


def render_dashboard_html(
    template_path: Path,
    bundle: dict,
    kpis: dict,
    df: pd.DataFrame,
    tier_chart_b64: str,
    pytest_chart_b64: str,
) -> str:
    """Render the suite dashboard HTML by substituting {{TOKEN}}-style
    placeholders in the template. A lightweight manual substitution is used
    (rather than a templating-engine dependency) since this module has no
    confirmed information about which templating library, if any, the
    per-BP dashboard templates use.

    Signature is unchanged from the prior version so the notebook's own
    Section 7 cell (already real-run and independently verified once) does
    not need to change: `tier_chart_b64` / `pytest_chart_b64` are still
    accepted and still embedded, now as the static/print/accessible-fallback
    images inside a collapsible section, alongside new interactive
    client-side SVG charts built from `build_suite_chart_payload`.
    """
    template = Path(template_path).read_text(encoding="utf-8")

    rows_html = []
    for _, row in df.iterrows():
        rc = row["record_count"]
        # pandas coerces a mixed int/None column to float64, turning a real,
        # already-confirmed absence (e.g. BP1-6 have no population-scale
        # record count) into NaN rather than None -- pd.isna() catches both
        # NaN and None so a genuinely-missing value never gets formatted
        # (formatting NaN with ":," silently prints the literal text "nan").
        record_cell = f"<td>{int(rc):,}</td>" if not pd.isna(rc) else "<td>&mdash;</td>"
        rows_html.append(
            "<tr>"
            f"<td>{_esc(row['bp'])}</td>"
            f"<td>{_esc(row['bp_name'])}</td>"
            f"<td>{_esc(row['champion'])}</td>"
            f"<td>{_esc(row['tier'])}</td>"
            f"<td>{_esc(row['tier_source'])}</td>"
            f"<td>{_esc(row['disparate_impact_status'])}</td>"
            + record_cell
            + f"<td>{_esc(row['generated_at_utc'])}</td>"
            f"<td>{_esc(row['smart_suggestion'])}</td>"
            "</tr>"
        )
    bp_table_rows = "\n".join(rows_html)

    tier_counts_rows = "\n".join(
        f"<tr><td>{_esc(tier)}</td><td>{count}</td></tr>" for tier, count in kpis["tier_counts"].items()
    )

    bp8 = bundle.get("bp8", {})

    bp8_gold_rows = (
        "\n".join(
            f"<tr><td>{_esc(t.get('category', t.get('filename', '?')))}</td>"
            f"<td>{_esc(t.get('filename'))}</td><td>{_esc(t.get('n_rows'))}</td>"
            f"<td>Gate 2</td></tr>"
            for t in (bp8.get("gold_tables") or [])
            if isinstance(t, dict)
        )
        + "\n"
        + "\n".join(
            f"<tr><td>{_esc(t.get('category', t.get('filename', '?')))}</td>"
            f"<td>{_esc(t.get('filename'))}</td><td>{_esc(t.get('n_rows'))}</td>"
            f"<td>Gate 3</td></tr>"
            for t in (bp8.get("gate3_gold_tables") or [])
            if isinstance(t, dict)
        )
    )

    chart_payload = build_suite_chart_payload(bundle, kpis, df)
    suite_data_json = json.dumps(chart_payload, default=str)

    replacements = {
        "SUITE_TITLE": "Customer360 Navigator Enterprise Suite — Executive Rollup",
        "N_BPS_TOTAL": str(kpis["n_bps_total"]),
        "N_BPS_FULLY_COMPLETE_GATE7": str(kpis["n_bps_fully_complete_gate7"]),
        "N_BPS_RECOMMENDED_FOR_PRODUCTION": str(kpis["n_bps_recommended_for_production"]),
        "N_BPS_DISPARATE_IMPACT_FLAGGED": str(kpis["n_bps_disparate_impact_flagged"]),
        "TOTAL_PYTEST_PASSED": str(kpis["total_pytest_passed_across_suite"]),
        "N_PYTEST_CONTRIBUTING_BPS": str(kpis["n_pytest_passed_contributing_bps"]),
        "TOTAL_RECORDS": f"{kpis['total_decision_or_gold_records_across_suite']:,}",
        "N_RECORD_CONTRIBUTING_BPS": str(kpis["n_record_count_contributing_bps"]),
        "BP_TABLE_ROWS": bp_table_rows,
        "TIER_COUNTS_ROWS": tier_counts_rows,
        "TIER_CHART_B64": tier_chart_b64,
        "PYTEST_CHART_B64": pytest_chart_b64,
        "BP8_GATE1_STATUS": "Confirmed" if bp8.get("gate1_confirmed") else "Not confirmed",
        "BP8_GATE1_GENERATED_AT": _esc(bp8.get("gate1_generated_at_utc")),
        "BP8_GATE2_STATUS": "Confirmed" if bp8.get("gate2_confirmed") else "Not confirmed",
        "BP8_KPI_CATEGORIES_READY": str(bp8.get("n_kpi_categories_ready")),
        "BP8_KPI_CATEGORIES_DEFERRED": str(bp8.get("n_kpi_categories_deferred")),
        "BP8_GOLD_TABLES_WRITTEN": str(bp8.get("gold_tables_written_count")),
        "BP8_GATE3_STATUS": _esc(bp8.get("gate3_status")),
        "BP8_GOLD_TABLE_ROWS": bp8_gold_rows,
        "BP8_SMART_SUGGESTION": _esc(bp8.get("smart_suggestion")),
        "STORY_TIER": _esc(story_tier(kpis)),
        "STORY_DISPARATE_IMPACT": _esc(story_disparate_impact(kpis)),
        "STORY_RECORDS": _esc(story_records(kpis)),
        "STORY_PYTEST": _esc(story_pytest(kpis)),
        "STORY_BP8": _esc(story_bp8(bp8)),
        "STORY_TIMELINE": _esc(story_generated_dates(bundle)),
        "SUITE_DATA_JSON": suite_data_json,
        "PALETTE_PRIMARY_NAVY": PALETTE["primary_navy"],
        "PALETTE_ACCENT_BLUE": PALETTE["accent_blue"],
        "PALETTE_SURFACE_LIGHT": PALETTE["surface_light"],
        "PALETTE_INK": PALETTE["ink"],
        "PALETTE_INK_MUTED": PALETTE["ink_muted"],
        "PALETTE_SUCCESS_GREEN": PALETTE["success_green"],
        "PALETTE_WARNING_AMBER": PALETTE["warning_amber"],
        "PALETTE_DANGER_RED": PALETTE["danger_red"],
        "PALETTE_NEUTRAL_GRAY": PALETTE["neutral_gray"],
        "HERO_GRADIENT_1": HERO_GRADIENT[0],
        "HERO_GRADIENT_2": HERO_GRADIENT[1],
        "HERO_GRADIENT_3": HERO_GRADIENT[2],
    }

    html = template
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _esc(value: Any) -> str:
    # A pandas column holding a real per-BP absence (e.g. BP5 has no
    # champion field, BP1/BP2 pre-date the disparate-impact check) can
    # coerce that already-confirmed None into float NaN depending on the
    # column's dtype -- pd.isna() catches both so a genuine absence always
    # renders as the same "&mdash;" placeholder, never the literal text
    # "nan" or "None".
    try:
        is_missing = value is None or pd.isna(value)
    except (TypeError, ValueError):
        # pd.isna() raises on some non-scalar types; anything reaching
        # that path is a real value, not a missing one.
        is_missing = False
    if is_missing:
        return "&mdash;"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# DOCX report
# ---------------------------------------------------------------------------


def write_docx_report(output_path: Path, bundle: dict, kpis: dict, df: pd.DataFrame) -> None:
    """Write a short (~4-8 page) executive DOCX report. python-docx is used,
    consistent with this project's DOCX-output convention for per-BP
    executive rollups. Includes a Smart Suggestions section (rule-based,
    see `compute_smart_suggestion` / `compute_bp8_smart_suggestion` --
    never AI-generated free text or assumption-based content)."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()

    title = doc.add_heading("Customer360 Navigator Enterprise Suite", level=0)
    title.runs[0].font.color.rgb = RGBColor.from_string(PALETTE["primary_navy"].lstrip("#"))
    doc.add_heading("Suite-Wide Executive Rollup (New, Additive Capstone Report)", level=1)

    intro = doc.add_paragraph()
    intro.add_run(
        "This report aggregates the already-produced Gate-7 executive rollups of "
        "BP1 through BP7, plus BP8's own Gate1/Gate2/Gate3 status, into one "
        "consolidated view. It is a new, additive deliverable requested directly "
        "by the project owner -- it is not part of the original Master Plan -- "
        "and it is strictly read-only over every BP1-BP8 artifact it summarizes. "
        "No dollar-impact figure, illustrative number, or assumption-based claim "
        "appears anywhere in this report, consistent with this project's "
        "project-wide ban on financial-impact and assumption-based content. Its "
        "Smart Suggestions section (below) is likewise rule-based, derived only "
        "from each BP's own already-real status fields -- never AI-generated "
        "free text."
    )

    doc.add_heading("Suite KPI Summary", level=1)
    kpi_lines = [
        f"Business problems in the suite: {kpis['n_bps_total']}",
        f"BP1-BP7 with a completed Gate 7 rollup: {kpis['n_bps_fully_complete_gate7']} of 7",
        f"BP1-BP7 carrying a RECOMMENDED FOR PRODUCTION tier: "
        f"{kpis['n_bps_recommended_for_production']} of {kpis['n_bps_fully_complete_gate7']}",
        f"BPs flagged for disparate impact: {kpis['n_bps_disparate_impact_flagged']} "
        f"(not-applicable: {kpis['disparate_impact_counts']['not_applicable']}, "
        f"structurally no check: {kpis['disparate_impact_counts']['structurally_no_check']})",
        f"Total pytest-passed across the suite: {kpis['total_pytest_passed_across_suite']} "
        f"(summed over {kpis['n_pytest_passed_contributing_bps']} BP(s) whose Gate 6 "
        "governance block this rollup reads)",
        f"Total decision/gold records represented: "
        f"{kpis['total_decision_or_gold_records_across_suite']:,} "
        f"(summed over {kpis['n_record_count_contributing_bps']} BP(s) exposing a "
        "population-scale record count)",
    ]
    for line in kpi_lines:
        doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("Tier Distribution (BP1-BP7)", level=2)
    for tier, count in kpis["tier_counts"].items():
        doc.add_paragraph(f"{tier}: {count} BP(s)", style="List Bullet")

    doc.add_heading("Per-BP Status", level=1)
    for bp_key in BP_ORDER:
        r = bundle[bp_key]
        p = doc.add_paragraph()
        run = p.add_run(f"{bp_key.upper()} -- {r.bp_name}")
        run.bold = True
        run.font.size = Pt(12)
        detail = doc.add_paragraph()
        champion_text = (
            f"Champion ({r.champion_field}): {r.champion}. "
            if r.champion_field is not None
            else "Champion: not present in this BP's own Gate 7 manifest (real schema gap). "
        )
        tier_text = (
            f"Production tier ({r.tier_source}): {r.tier}. "
            if r.tier
            else "Production tier: not present in this BP's own Gate 7 manifest (real schema gap). "
        )
        detail.add_run(
            champion_text + tier_text + f"Disparate-impact status: {r.disparate_impact_status}. "
            f"Gate 7 generated: {r.generated_at_utc}."
        )

    doc.add_heading("BP8 -- Executive Product Analytics", level=1)
    bp8 = bundle["bp8"]
    doc.add_paragraph(
        f"Gate 1 (aggregation scope): "
        f"{'real-run-confirmed' if bp8['gate1_confirmed'] else 'not confirmed'} "
        f"as of {bp8['gate1_generated_at_utc']}."
    )
    doc.add_paragraph(
        f"Gate 2 (gold table build): "
        f"{'real-run-confirmed' if bp8['gate2_confirmed'] else 'not confirmed'}, "
        f"{bp8['n_kpi_categories_ready']} KPI categories ready, "
        f"{bp8['n_kpi_categories_deferred']} deferred, "
        f"{bp8['gold_tables_written_count']} Gold tables written."
    )
    doc.add_paragraph(f"Gate 3 (decision-engine KPI layer): {bp8['gate3_status']}.")

    doc.add_heading("Smart Suggestions (Rule-Based, Not AI-Generated Free Text)", level=1)
    doc.add_paragraph(
        "Each line below is the fixed, deterministic output of a rule table over that "
        "BP's own already-real tier / disparate-impact / gate-status fields (see "
        "compute_smart_suggestion / compute_bp8_smart_suggestion in "
        "suite_rollup_helpers.py) -- never a forecast, dollar figure, or speculative claim."
    )
    for bp_key in BP_ORDER:
        r = bundle[bp_key]
        p = doc.add_paragraph()
        run = p.add_run(f"{bp_key.upper()}: ")
        run.bold = True
        p.add_run(r.smart_suggestion)
    p = doc.add_paragraph()
    run = p.add_run("BP8: ")
    run.bold = True
    p.add_run(bp8.get("smart_suggestion", ""))

    doc.add_heading("Closing Note", level=1)
    doc.add_paragraph(
        "The suite's own final decision layer is a human-built Power BI Desktop "
        "(.pbix) file, per the project's own Master Plan Section 19. That build "
        "is explicitly out of scope for any notebook -- including this one -- to "
        "produce."
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


# ---------------------------------------------------------------------------
# PDF report (converted from the DOCX above -- never a second, independently
# authored document, so its content always matches the DOCX exactly)
# ---------------------------------------------------------------------------


def write_pdf_report(docx_path: Path, pdf_path: Path) -> dict:
    """Convert the already-written DOCX report to PDF.

    This deliberately does NOT re-author the report content in a second code
    path (e.g. reportlab) -- it converts the DOCX this module just wrote, so
    the PDF is always byte-for-byte the same content as the Word report,
    never a second place a discrepancy could creep in.

    Tries, in order, whichever converter is actually available in the
    environment this notebook runs in (Windows, per this project's standing
    environment):
      1. `docx2pdf` (drives a real Microsoft Word installation via COM --
         the standard choice on Windows when Word is installed).
      2. `soffice`/`libreoffice` on PATH, invoked as a subprocess (works if
         LibreOffice is installed instead of/alongside Word).

    If neither is available, this function does NOT raise or crash the
    notebook -- it returns a dict with `"status": "skipped"` and a plain-
    English reason, so every OTHER output (HTML/DOCX/XLSX/PPTX) still gets
    written even in an environment with neither Word nor LibreOffice
    installed. The notebook's own integrity-check cell treats this as a
    WARN, never a hard FAIL, for the same reason.
    """
    docx_path = Path(docx_path)
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Attempt 1: docx2pdf (Microsoft Word COM automation -- Windows/macOS).
    try:
        from docx2pdf import convert as _docx2pdf_convert

        _docx2pdf_convert(str(docx_path), str(pdf_path))
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return {"status": "written", "method": "docx2pdf", "path": str(pdf_path)}
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure
        # here (not installed, no Word installed, COM error) falls through
        # to the soffice attempt rather than crashing the notebook.
        docx2pdf_error = str(exc)
    else:
        docx2pdf_error = "docx2pdf ran but produced no output file"

    # Attempt 2: soffice / libreoffice on PATH.
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice_bin:
        try:
            # No shell=True: args are a fixed list built from shutil.which()'s own resolved
            # binary path plus this function's own Path arguments (never external/untrusted
            # input) - same verified-safe shape as src/deployment/readiness_verdict.py's own
            # subprocess.run call. Suppressed on the flagged line, below.
            result = subprocess.run(  # nosec B603
                [
                    soffice_bin,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(pdf_path.parent),
                    str(docx_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            converted = pdf_path.parent / (docx_path.stem + ".pdf")
            if converted.exists() and converted != pdf_path:
                converted.replace(pdf_path)
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                return {"status": "written", "method": "soffice", "path": str(pdf_path)}
            soffice_error = f"soffice exited {result.returncode}; stderr: {result.stderr[-500:]}"
        except Exception as exc:  # noqa: BLE001
            soffice_error = str(exc)
    else:
        soffice_error = "soffice/libreoffice not found on PATH"

    return {
        "status": "skipped",
        "reason": (
            "Neither docx2pdf (Microsoft Word) nor soffice/libreoffice was able to "
            f"convert the DOCX to PDF. docx2pdf: {docx2pdf_error}. soffice: {soffice_error}. "
            "The HTML/DOCX/XLSX/PPTX outputs were written regardless -- install "
            "Microsoft Word or LibreOffice and re-run this notebook to also get the PDF."
        ),
        "path": None,
    }


# ---------------------------------------------------------------------------
# XLSX workbook
# ---------------------------------------------------------------------------


def write_xlsx_workbook(output_path: Path, bundle: dict, kpis: dict, df: pd.DataFrame) -> None:
    """Write a suite-KPI sheet plus a per-BP status sheet."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _kv(metric: str) -> dict:
        return {"metric": metric, "value": kpis[metric]}

    kpi_rows = [
        _kv("n_bps_total"),
        _kv("n_bps_fully_complete_gate7"),
        _kv("n_bps_recommended_for_production"),
        _kv("n_bps_disparate_impact_flagged"),
        _kv("total_pytest_passed_across_suite"),
        _kv("n_pytest_passed_contributing_bps"),
        _kv("total_decision_or_gold_records_across_suite"),
        _kv("n_record_count_contributing_bps"),
        {"metric": "bp8_gate1_confirmed", "value": kpis["bp8_gate1_confirmed"]},
        {"metric": "bp8_gate2_confirmed", "value": kpis["bp8_gate2_confirmed"]},
        {"metric": "bp8_n_kpi_categories_ready", "value": kpis["bp8_n_kpi_categories_ready"]},
        {"metric": "bp8_n_kpi_categories_deferred", "value": kpis["bp8_n_kpi_categories_deferred"]},
        {"metric": "bp8_gold_tables_written_count", "value": kpis["bp8_gold_tables_written_count"]},
        {"metric": "bp8_gate3_status", "value": kpis["bp8_gate3_status"]},
    ]
    kpi_df = pd.DataFrame(kpi_rows)

    tier_df = pd.DataFrame([{"tier": t, "n_bps": c} for t, c in kpis["tier_counts"].items()])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        kpi_df.to_excel(writer, sheet_name="suite_kpis", index=False)
        tier_df.to_excel(writer, sheet_name="tier_distribution", index=False)
        df.to_excel(writer, sheet_name="per_bp_status", index=False)


# ---------------------------------------------------------------------------
# PPTX deck
# ---------------------------------------------------------------------------


def write_pptx_deck(
    output_path: Path,
    bundle: dict,
    kpis: dict,
    df: pd.DataFrame,
    tier_chart_png_bytes: bytes,
) -> None:
    """Write a ~6-10 slide executive deck."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    blank = prs.slide_layouts[6]
    title_layout = prs.slide_layouts[0]
    bullet_layout = prs.slide_layouts[1]

    navy = RGBColor.from_string(PALETTE["primary_navy"].lstrip("#"))

    # Slide 1: title
    slide = prs.slides.add_slide(title_layout)
    slide.shapes.title.text = "Customer360 Navigator Enterprise Suite"
    slide.shapes.title.text_frame.paragraphs[0].font.color.rgb = navy
    slide.placeholders[1].text = "Suite-Wide Executive Rollup"

    # Slide 2: suite KPI overview
    slide = prs.slides.add_slide(bullet_layout)
    slide.shapes.title.text = "Suite KPI Overview"
    body = slide.placeholders[1].text_frame
    body.text = f"BPs in suite: {kpis['n_bps_total']}"
    lines = [
        f"BP1-BP7 with completed Gate 7: {kpis['n_bps_fully_complete_gate7']} of 7",
        f"Recommended for production: {kpis['n_bps_recommended_for_production']}",
        f"Disparate-impact flagged: {kpis['n_bps_disparate_impact_flagged']}",
        f"Total pytest passed (suite): {kpis['total_pytest_passed_across_suite']} "
        f"(n={kpis['n_pytest_passed_contributing_bps']} BPs)",
        f"Total decision/gold records: {kpis['total_decision_or_gold_records_across_suite']:,} "
        f"(n={kpis['n_record_count_contributing_bps']} BPs)",
    ]
    for line in lines:
        p = body.add_paragraph()
        p.text = line
        p.font.size = Pt(18)

    # Slides 3-4: per-BP status table (split BP1-4, BP5-7+BP8)
    for chunk_name, chunk_keys in (
        ("BP1-BP4 Status", BP_ORDER[:4]),
        ("BP5-BP7 Status", BP_ORDER[4:]),
    ):
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(Inches(0.4), Inches(0.3), Inches(9), Inches(0.6))
        tb.text_frame.text = chunk_name
        tb.text_frame.paragraphs[0].font.size = Pt(24)
        tb.text_frame.paragraphs[0].font.bold = True
        tb.text_frame.paragraphs[0].font.color.rgb = navy

        rows = len(chunk_keys) + 1
        cols = 4
        table_shape = slide.shapes.add_table(
            rows, cols, Inches(0.4), Inches(1.0), Inches(9), Inches(0.5 * rows)
        )
        table = table_shape.table
        headers = ["BP", "Champion", "Tier", "Disparate Impact"]
        for c, h in enumerate(headers):
            table.cell(0, c).text = h
        for i, bp_key in enumerate(chunk_keys, start=1):
            r = bundle[bp_key]
            table.cell(i, 0).text = bp_key.upper()
            table.cell(i, 1).text = r.champion if r.champion else "— (not in manifest)"
            table.cell(i, 2).text = r.tier if r.tier else "— (not in manifest)"
            table.cell(i, 3).text = str(r.disparate_impact_status)

    # Slide 5: tier distribution chart
    slide = prs.slides.add_slide(blank)
    tb = slide.shapes.add_textbox(Inches(0.4), Inches(0.3), Inches(9), Inches(0.6))
    tb.text_frame.text = "Production-Recommendation Tier Distribution"
    tb.text_frame.paragraphs[0].font.size = Pt(24)
    tb.text_frame.paragraphs[0].font.bold = True
    tb.text_frame.paragraphs[0].font.color.rgb = navy
    slide.shapes.add_picture(BytesIO(tier_chart_png_bytes), Inches(1.0), Inches(1.2), width=Inches(8))

    # Slide 6: BP8
    slide = prs.slides.add_slide(bullet_layout)
    slide.shapes.title.text = "BP8 -- Executive Product Analytics"
    body = slide.placeholders[1].text_frame
    bp8 = bundle["bp8"]
    body.text = f"Gate 1: {'confirmed' if bp8['gate1_confirmed'] else 'not confirmed'}"
    for line in [
        f"Gate 2: {bp8['n_kpi_categories_ready']} KPI categories ready, "
        f"{bp8['gold_tables_written_count']} Gold tables written",
        f"Gate 3: {bp8['gate3_status']}",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.font.size = Pt(18)

    # Slide 7: Smart Suggestions
    slide = prs.slides.add_slide(bullet_layout)
    slide.shapes.title.text = "Smart Suggestions (Rule-Based)"
    body = slide.placeholders[1].text_frame
    body.text = f"BP1: {bundle['bp1'].smart_suggestion}"
    for bp_key in BP_ORDER[1:]:
        p = body.add_paragraph()
        p.text = f"{bp_key.upper()}: {bundle[bp_key].smart_suggestion}"
        p.font.size = Pt(12)
    p = body.add_paragraph()
    p.text = f"BP8: {bp8.get('smart_suggestion', '')}"
    p.font.size = Pt(12)

    # Slide 8: closing
    slide = prs.slides.add_slide(bullet_layout)
    slide.shapes.title.text = "Closing Note"
    body = slide.placeholders[1].text_frame
    body.text = (
        "The suite's final decision layer is a human-built Power BI Desktop "
        "(.pbix) file, per Master Plan Section 19 -- out of scope for any "
        "notebook to build."
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))


# ---------------------------------------------------------------------------
# Suite manifest assembly (assembly-only -- no I/O, mirrors BP8 Gate 3's
# gate3_manifest() shape)
# ---------------------------------------------------------------------------


def suite_rollup_manifest(
    bundle: dict,
    kpis: dict,
    fingerprints_before: dict,
    fingerprints_after: dict,
    output_paths: dict,
    generated_at_utc: str,
    pdf_result: Optional[dict] = None,
) -> dict:
    """Assemble the suite's own manifest dict. Pure assembly -- no file I/O
    happens inside this function; the notebook does the
    Path.write_text/json.dump.

    `pdf_result` (optional) is the dict `write_pdf_report` returned -- kept
    OUT of `output_paths` deliberately, because PDF conversion depends on
    Word/LibreOffice being installed and is allowed to be genuinely absent
    in a given environment (see `write_pdf_report`'s docstring); the
    notebook's own integrity checks treat it as a soft WARN, never a hard
    FAIL, for the same reason -- it must never be folded into the
    hard-required `output_paths` existence check.
    """
    result = {
        "report_id": "00_suite_executive_rollup",
        "report_name": "Customer360 Navigator Enterprise Suite -- Executive Rollup",
        "is_master_plan_gate": False,
        "read_only_over_bp1_bp8": True,
        "generated_at_utc": generated_at_utc,
        "contains_financial_impact_section": False,
        "contains_assumption_based_content": False,
        "n_bps_total": kpis["n_bps_total"],
        "n_bps_fully_complete_gate7": kpis["n_bps_fully_complete_gate7"],
        "n_bps_recommended_for_production": kpis["n_bps_recommended_for_production"],
        "tier_counts": kpis["tier_counts"],
        "disparate_impact_counts": kpis["disparate_impact_counts"],
        "n_bps_disparate_impact_flagged": kpis["n_bps_disparate_impact_flagged"],
        "total_pytest_passed_across_suite": kpis["total_pytest_passed_across_suite"],
        "n_pytest_passed_contributing_bps": kpis["n_pytest_passed_contributing_bps"],
        "pytest_passed_contributing_bps": kpis["pytest_passed_contributing_bps"],
        "total_decision_or_gold_records_across_suite": kpis["total_decision_or_gold_records_across_suite"],
        "n_record_count_contributing_bps": kpis["n_record_count_contributing_bps"],
        "record_count_contributing_bps": kpis["record_count_contributing_bps"],
        "financial_assumption_audit": kpis["financial_assumption_audit"],
        "bp8_gate1_confirmed": kpis["bp8_gate1_confirmed"],
        "bp8_gate2_confirmed": kpis["bp8_gate2_confirmed"],
        "bp8_n_kpi_categories_ready": kpis["bp8_n_kpi_categories_ready"],
        "bp8_n_kpi_categories_deferred": kpis["bp8_n_kpi_categories_deferred"],
        "bp8_gold_tables_written_count": kpis["bp8_gold_tables_written_count"],
        "bp8_gate3_status": kpis["bp8_gate3_status"],
        "bp8_gate3_n_kpi_tables_ready": kpis["bp8_gate3_n_kpi_tables_ready"],
        "source_file_fingerprints_before": fingerprints_before,
        "source_file_fingerprints_after": fingerprints_after,
        "output_paths": output_paths,
        "power_bi_pbix_build": "out_of_scope_human_task_master_plan_section_19",
    }
    if pdf_result is not None:
        result["report_pdf"] = pdf_result
    return result
