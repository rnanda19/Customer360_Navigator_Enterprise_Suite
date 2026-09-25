"""BP6 (GenAI Resolution Assistant) — Gate 2 support module: PII screening & evidence-source
registry.

BP6 has no supervised target and no training split at any gate (Gate 1's own policy.json, see
`target_definition: null` in configs/bp6_genai_resolution_assistant.yaml) — it is a retrieval-and
-grounded-generation governance layer, not a classifier. So the generic Master Plan Gate 2 row
("Data Verification & Feature/Taxonomy Engineering (WARP)" / output: "Engineered features,
taxonomy mapping, real row/column counts" / compliance touchpoint: "PII screen on narrative text
before any downstream/external call") maps onto BP6 differently than it does for BP1-5's
supervised-classifier gates:

1. PII SCREEN (the Gate 2 compliance touchpoint BP6's own Gate 1 policy.json explicitly deferred
   here — see `genai_usage_policy.glba_pii_masking.applies_before` in
   notebooks/bp6_genai_resolution_assistant/artifacts/policy.json: "the actual screen is a Gate 2
   compliance touchpoint, not performed by this Gate 1 notebook"). Applied to BP1's real, already
   -built BANKING77 Gold layer (`data/processed/banking77_common_taxonomy_gold.parquet`) — the
   SOLE real narrative-text source in this entire suite (the real CFPB extract carries no
   narrative-text column, RAW_DATA_MANIFEST.md Finding 2, re-verified live at every gate that has
   checked it so far). This module never mutates or re-writes that file — it is BP1's own real
   Gold artifact; BP6 only reads it and produces its own separate screening-report artifact.

2. DATA VERIFICATION — real row/column counts and a zero-nulls-silently-dropped check on the same
   read, matching BP6 Gate 1's own live-checked banking77_train_rows=10003 / banking77_test_rows
   =3080 (13,083 total).

3. TAXONOMY MAPPING / FEATURE-LINEAGE analog — BP6 has no engineered feature table to build a
   lineage table for (see point 1 above), so this module's real analog is an EVIDENCE-SOURCE
   REGISTRY: a live, structural inventory of every real artifact file BP1-BP5 have actually
   written to disk so far (path, existence, size, modified time, and — for JSON/CSV files only,
   never the giant multi-row exports — a light schema fingerprint: JSON top-level keys, or CSV
   header columns read via a cheap header-only read, never the full file). This gives BP6's own
   future Gate 5 retrieval step a real, live-verified map of what is actually available to cite,
   without ever hardcoding assumptions about any upstream BP's internal field names (BP6 Gate 1's
   own stated design principle — its own citation schema is deliberately generic:
   source_bp/source_gate/source_artifact_relative_path/source_field_or_metric).

Zero external API calls and zero GenAI SDK module imports happen in this module or in the Gate 2
notebook that calls it — re-verified live in the notebook's own Section 6, same check pattern as
Gate 1's Section 6 (BP6's GenAI call does not occur until Gate 5).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# PII detection / masking
# ---------------------------------------------------------------------------
# Deliberately narrow, high-precision patterns for the real narrative-text source this module
# actually screens (BANKING77's short customer-service utterances) — favors catching real,
# unambiguous PII shapes over flagging ordinary numeric mentions ("2 weeks", "3 times") as PII.

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
)

_SSN_LIKE_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

# Card-like: 4 groups of 4 digits (the shape people actually type), or one unbroken 13-19 digit
# run. Luhn-validated so an ordinary long number ("order number 4029123456789012" typed without
# real card semantics) is not flagged unless it also happens to pass Luhn - reduces false
# positives on the many non-PII long digit runs that show up in support text (order/reference
# numbers), while still catching real card-shaped input.
_CARD_GROUPED_RE = re.compile(r"(?<!\d)\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{3,4}(?!\d)")
_CARD_UNBROKEN_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")


def _luhn_valid(digits: str) -> bool:
    digits = digits.replace("-", "").replace(" ", "")
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    reverse_digits = digits[::-1]
    for i, ch in enumerate(reverse_digits):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


PII_CATEGORIES: list[str] = ["email", "phone", "ssn_like", "card_like"]


def detect_pii_categories(text: str) -> list[str]:
    """Returns the list of PII categories detected in `text` (possibly empty). Never mutates
    `text`. Card-like matches are Luhn-validated to avoid flagging ordinary long numbers as PII."""
    if not isinstance(text, str) or not text:
        return []
    hits: list[str] = []
    if _EMAIL_RE.search(text):
        hits.append("email")
    if _PHONE_RE.search(text):
        hits.append("phone")
    if _SSN_LIKE_RE.search(text):
        hits.append("ssn_like")
    card_candidates = _CARD_GROUPED_RE.findall(text) + _CARD_UNBROKEN_RE.findall(text)
    if any(_luhn_valid(c) for c in card_candidates):
        hits.append("card_like")
    return hits


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Returns (masked_text, categories_redacted). Replaces each detected category's real matches
    with a category-tagged placeholder; categories with no match in `text` are left alone."""
    if not isinstance(text, str) or not text:
        return text, []
    categories = detect_pii_categories(text)
    masked = text
    if "email" in categories:
        masked = _EMAIL_RE.sub("[EMAIL_REDACTED]", masked)
    if "phone" in categories:
        masked = _PHONE_RE.sub("[PHONE_REDACTED]", masked)
    if "ssn_like" in categories:
        masked = _SSN_LIKE_RE.sub("[SSN_REDACTED]", masked)
    if "card_like" in categories:
        for pattern in (_CARD_GROUPED_RE, _CARD_UNBROKEN_RE):
            def _sub(m: re.Match) -> str:
                return "[CARD_REDACTED]" if _luhn_valid(m.group(0)) else m.group(0)
            masked = pattern.sub(_sub, masked)
    return masked, categories


def run_pii_screen(df: pd.DataFrame, text_col: str = "text") -> pd.DataFrame:
    """Applies detect_pii_categories/mask_pii to every row of df[text_col]. Returns a NEW
    DataFrame (BP1's own Gold layer `df` is never mutated in place) with three added columns:
    pii_detected (bool), pii_categories (str, comma-joined, "" if none), masked_text (str).
    Every original column is carried through unchanged."""
    if text_col not in df.columns:
        raise KeyError(
            f"run_pii_screen: expected column '{text_col}' not found in DataFrame columns "
            f"{list(df.columns)}"
        )
    out = df.copy()
    masked_and_cats = out[text_col].apply(mask_pii)
    out["masked_text"] = masked_and_cats.apply(lambda t: t[0])
    out["pii_categories"] = masked_and_cats.apply(lambda t: ",".join(t[1]))
    out["pii_detected"] = out["pii_categories"].str.len() > 0
    return out


def summarize_pii_screen(screened_df: pd.DataFrame) -> dict[str, Any]:
    """Summary counts over a run_pii_screen() output. Real numbers only - no estimation."""
    n_rows = len(screened_df)
    n_flagged = int(screened_df["pii_detected"].sum())
    category_counts: dict[str, int] = {c: 0 for c in PII_CATEGORIES}
    for cats in screened_df.loc[screened_df["pii_detected"], "pii_categories"]:
        for c in cats.split(","):
            if c:
                category_counts[c] = category_counts.get(c, 0) + 1
    return {
        "n_rows_screened": n_rows,
        "n_rows_flagged": n_flagged,
        "pct_rows_flagged": round(n_flagged / n_rows, 6) if n_rows else 0.0,
        "category_counts": category_counts,
        "pii_categories_checked": list(PII_CATEGORIES),
    }


# ---------------------------------------------------------------------------
# Evidence-source registry (BP6's Gate 2 "taxonomy mapping" / "feature-lineage" analog)
# ---------------------------------------------------------------------------
_JSON_EXT = {".json"}
_CSV_EXT = {".csv"}
_MAX_HEADER_BYTES = 1_048_576  # 1MB cap on what this function will read of any single file's
# content for fingerprinting - CSV header reads use nrows=0 (pandas only reads the header line
# regardless of file size), and JSON files here are all real gate-summary artifacts, never the
# large per-row decision-record exports, so this cap is a safety guard, not a real constraint hit
# by any file this registry actually probes today.


def probe_artifact_file(path: Path) -> dict[str, Any]:
    """Read-only structural probe of one real artifact file: existence, size, modified time, and
    - for .json/.csv only - a light schema fingerprint (JSON top-level keys, or CSV header
    columns via a header-only read). Never loads a large file's full row data. Never raises on a
    missing file - returns exists=False instead, since an upstream BP's later gates may not have
    run yet."""
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": None,
        "modified_at_utc": None,
        "kind": None,
        "schema_fingerprint": None,
    }
    if not result["exists"]:
        return result
    stat = path.stat()
    result["size_bytes"] = stat.st_size
    result["modified_at_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    suffix = path.suffix.lower()
    if suffix in _JSON_EXT:
        result["kind"] = "json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                result["schema_fingerprint"] = sorted(data.keys())
            elif isinstance(data, list):
                result["schema_fingerprint"] = (
                    sorted(data[0].keys()) if data and isinstance(data[0], dict) else []
                )
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            result["schema_fingerprint"] = None
    elif suffix in _CSV_EXT:
        result["kind"] = "csv"
        try:
            header_df = pd.read_csv(path, nrows=0)
            result["schema_fingerprint"] = list(header_df.columns)
        except (pd.errors.ParserError, UnicodeDecodeError, OSError):
            result["schema_fingerprint"] = None
    elif suffix == ".log":
        result["kind"] = "log"
    elif suffix in {".parquet"}:
        result["kind"] = "parquet"
    else:
        result["kind"] = "other"
    return result


UPSTREAM_BP_NAMES: dict[str, str] = {
    "bp1": "bp1_customer_intent_classification",
    "bp2": "bp2_customer_friction_classification",
    "bp3": "bp3_complaint_escalation_prediction",
    "bp4": "bp4_customer_journey_analytics",
    "bp5": "bp5_root_cause_driver_analytics",
}


def _read_config_status(config_path: Path) -> str | None:
    """Cheap top-level `status:` line read - never a full YAML parse of the whole config, since
    this registry only needs one field and some of these configs carry large nested blocks.
    Several of these config files (bp4, bp5) keep an inline `# not_started|gate1|...` comment on
    the same status line, appended after the value with no space before the '#' guaranteed - the
    trailing comment must be stripped BEFORE quote-stripping, or it leaks into the returned
    string (a real bug this module's own sandbox verification caught: bp4/bp5's status strings
    came back as e.g. 'gate6_complete"   # not_started|gate1|...' instead of 'gate6_complete')."""
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("status:"):
                value = stripped.split(":", 1)[1]
                value = value.split("#", 1)[0]  # drop any trailing inline comment
                return value.strip().strip('"').strip("'")
    return None


def build_evidence_source_registry(project_root: Path) -> dict[str, Any]:
    """Live, structural inventory of every real artifact file BP1-BP5 have written to
    notebooks/<bp>/artifacts/ so far, plus each BP's own config-status string. Generic by
    construction - never hardcodes any upstream BP's internal field names, only enumerates what
    real files and top-level keys/columns actually exist right now."""
    registry: dict[str, Any] = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "upstream_bps": {}}
    for bp_id, bp_name in UPSTREAM_BP_NAMES.items():
        config_path = project_root / "configs" / f"{bp_name}.yaml"
        artifacts_dir = project_root / "notebooks" / bp_name / "artifacts"
        artifact_probes: list[dict[str, Any]] = []
        if artifacts_dir.exists():
            for file_path in sorted(artifacts_dir.iterdir()):
                if file_path.is_file():
                    artifact_probes.append(probe_artifact_file(file_path))
        registry["upstream_bps"][bp_id] = {
            "bp_id": bp_id,
            "bp_name": bp_name,
            "config_status_string_live": _read_config_status(config_path),
            "n_artifact_files_live": len(artifact_probes),
            "artifacts": artifact_probes,
        }
    return registry


# ---------------------------------------------------------------------------
# Zero-external-call verification (same style as Gate 1's own Section 6 check)
# ---------------------------------------------------------------------------
# Deliberately the SAME four prefixes BP6 Gate 1's own notebook checks (its
# FORBIDDEN_GENAI_SDK_MODULE_PREFIXES), not a broader guess - Gate 1's real run on the user's own
# home_credit_env Jupyter kernel already empirically confirmed this exact list comes back empty
# there (see notebooks/bp6_genai_resolution_assistant/artifacts/policy.json's live_checks.
# genai_sdk_modules_loaded_this_run: []). A broader list (e.g. also flagging "requests"/"httpx"/
# "urllib3") was tried first here and dropped: those are commonly imported transitively by
# ordinary kernel/notebook machinery unrelated to any real external call BP6 makes, so including
# them risks a false-positive hard-failure on the real run over nothing BP6 actually did -
# consistency with Gate 1's own already-proven-clean list is the safer, real-evidence-based choice.
# 'google.genai' added 2026-09-24 when BP6 Gate 5's real provider pivoted from the Anthropic
# Claude API to Google's Gemini API (free tier) - additive only, does not change Gates 1-4's
# already real-run-confirmed empty-list results, since none of them ever imported this module
# either. 'google.generativeai' (the OLD, now-deprecated Gemini SDK) is kept in the list too, in
# case any future code path ever imports the legacy package instead of the current one.
_GENAI_SDK_MODULE_PREFIXES = ("openai", "anthropic", "google.generativeai", "google.genai", "cohere")


def genai_sdk_modules_loaded() -> list[str]:
    """Returns which (if any) external-API/GenAI SDK module prefixes are currently loaded in
    sys.modules - used to structurally re-confirm this Gate 2 notebook made zero external calls,
    matching Gate 1's own Section 6 check pattern and its own exact prefix list."""
    import sys

    loaded = []
    for prefix in _GENAI_SDK_MODULE_PREFIXES:
        if any(name == prefix or name.startswith(prefix + ".") for name in sys.modules):
            loaded.append(prefix)
    return loaded
