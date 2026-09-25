# BP3 - Complaint Escalation / Intervention Prediction - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end, plus a full disparate-impact investigation (Tier C proxy-feature audit + two Tier A fairness-aware retraining candidates), also real-run confirmed.

Target: binary `intervention_required` (1,048,575 rows; `Tags` barred from the feature set, used only as a read-only fairness-monitoring passthrough). First BP in the suite to carry a live ECOA/Regulation B disparate-impact check.

Champion: **xgboost** (5-model benchmark, top-5-only per explicit scope). Held-out test PR-AUC **0.3496**, recall **0.9424**, ROC-AUC **0.9762**.

**Real, disclosed finding:** `adverse_impact_ratio_tags = 0.139` (flagged against the 0.8 four-fifths-rule floor) on the `Tags` group. Diagnosed as MODEL-DRIVEN, not prevalence-driven (`recall_ratio=0.956` balanced, `fpr_ratio=0.132` not balanced). A proxy-feature audit found no single trained feature explains the gap (max Cramer's V 0.187). Two fairness-aware retraining candidates (FPR-targeted sample reweighting, v1 linear + v2 amplified) were built, real-run confirmed, and **not adopted** - both cost real PR-AUC/recall without closing the gap. **Final governance decision: ACCEPT_TIER_D** - the original xgboost champion ships unchanged, the finding is disclosed and monitored, not hidden or silently 'fixed'.

Standalone investigation notebooks (not numbered gates): `bp3_complaint_escalation_prediction_disparate_impact_investigation.ipynb`, `..._proxy_feature_audit.ipynb`, `..._fairness_aware_retraining_candidate.ipynb` (+ `_v2`).
