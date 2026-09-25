# Project Structure - LOCKED as of 2026-09-21

This folder layout is final as of the date above. Do not rename, move, or reorganize any folder here once a
notebook has written a path into a config file or a summary JSON.

## Why this is a hard rule (real, not hypothetical)
On the AMEX RiskIQ platform, a mid-project folder reorg (Phase 1 restructuring) left old notebooks and their
already-generated summary JSONs pointing at stale paths. This caused a chain of real bugs across multiple
notebooks (Notebook 27 Error 1/2, Notebook 34/35's path-resolution bugs) and forced a 3-then-4-candidate
path-resolver workaround (current nested path -> PILLAR_DIRS lookup -> legacy root path -> exact summary-JSON
path) that had to be retrofitted into every downstream notebook. On Home Credit, project_config.json's own
`pillar_dirs` dict was discovered to still hold pre-reorg paths for every pillar that existed before a folder
move - only pillars created fresh after the move were safe to trust. Both cost real debugging hours.

## Standing rule for this project
1. This structure is decided once, here, before Sprint 1 starts. No BP folder gets renamed after its first
   notebook is written.
2. If a genuine restructure is ever unavoidable, every path written into any `configs/*.yaml` or
   `*_summary.json` must be regenerated, not left stale - never patch downstream notebooks with a
   multi-candidate path resolver as a substitute for fixing the source config.
3. Every notebook resolves its own project root via an environment-variable override first, then a bounded
   upward walk from the notebook's own location - never a hardcoded absolute path.

## Top-level layout
- docs/ - BRD, FRD, RTM, architecture, data dictionary, Evidence Ledger, compliance mapping, the master plan
- data/{raw,processed,external} - gitignored; raw CFPB/BANKING77 extracts live here, once, never duplicated
- notebooks/ - 00_hardware_benchmark + one folder per BP (bp1_... through bp8_...)
- src/{taxonomy,features,models,reporting,utils} - the shared HYPER component library, imported from BP1 onward
- tests/ - shared/ plus one folder per BP, pytest
- models/ - trained artifacts per BP (gitignored binaries; folder structure tracked)
- reports/ - MODEL_CARD.md + CHANGELOG.md per BP
- powerbi/{gold_tables,pbix} - BP8's decision layer
- configs/ - per-BP YAML + resource_limits.yaml (WARP ceilings)
- .github/workflows/ - CI (lint, test, notebook-syntax-check, pre-commit)
- logs/ - gitignored run logs
- github_repo/ - staged packaging copy for the public GitHub push (see its own README.md for why this is
  separate from the working folders above)
- kaggle/ - Kaggle/Hugging Face packaging notes (see its own README.md - not directly applicable the way it
  was on AMEX/Home Credit; flagged, not assumed)
- linkedin/ - portfolio post drafts

## BP folder naming (final, do not change)
bp1_customer_intent_classification, bp2_customer_friction_classification, bp3_complaint_escalation_prediction,
bp4_customer_journey_analytics, bp5_root_cause_driver_analytics, bp6_genai_resolution_assistant,
bp7_customer_navigator_decision_engine, bp8_executive_product_analytics
