# Changelog

Repo-level build history. Per-BP changelogs (model/gate-level detail) live in `reports/<bp>/CHANGELOG.md`.
Every entry below corresponds to a real milestone logged in `docs/evidence_ledger/EVIDENCE_LEDGER.md`.

## 2026-09-26
- GitHub repository created and pushed live: `rnanda19/Customer360_Navigator_Enterprise_Suite`.

## 2026-09-25
- BP5, BP6, BP7, BP8 all closed — every gate real-run confirmed end to end.
- Suite-wide executive rollup (`00_suite_executive_rollup`) built, hardened, and real-run confirmed.
- BP1/BP2/BP4 model-persistence notebooks real-run confirmed (previously only sandbox-verified).
- Deployment-readiness-verdict modules delivered and independently spot-checked for BP5/6/7/8.
- One real bug found and fixed in `bp8_gold_table_builders.py` (empty-outcome `pl.concat` crash) —
  confirmed via a live regeneration the same day.
- Repository fully populated and pushed to GitHub for the first time.

## 2026-09-24
- BP3's disparate-impact investigation closed: Tier C proxy-feature audit, two Tier A fairness-aware
  retraining candidates (v1, v2) — both real-run, both rejected on the evidence. Final governance
  decision: accept and disclose (original champion unchanged).
- BP3 and BP4 hardening passes completed (model persistence, FastAPI services, deployment-readiness
  verdict, Docker packaging, CI).
- BP1/BP2 executive rollups retrofitted with the live-computed "Recommended for Production" field.

## 2026-09-23
- BP3 (Complaint Escalation Prediction) and BP4 (Customer Journey Analytics) both closed — all 6 gates +
  executive rollup real-run confirmed for each.
- BP3's real disparate-impact finding first surfaced (adverse impact ratio 0.139, flagged) and disclosed.

## 2026-09-22
- BP1 and BP2 both closed — all 6 gates + executive rollup real-run confirmed for each.
- AMEX-RiskIQ-grade hardening pass started for BP1/BP2 (packaging, model persistence, FastAPI, Docker, CI).

## 2026-09-21
- Project started. Hardware benchmark and data-acquisition/profiling notebooks real-run confirmed.
- BP1 Gates 1-2 built and real-run confirmed.
