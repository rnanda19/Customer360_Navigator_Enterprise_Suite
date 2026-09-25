# Model Registry

What's actually persisted on disk per business problem, and why some BPs have no entry here at all.

| BP | Persisted artifact | Champion | Real size | Fidelity check |
|---|---|---|---|---|
| BP1 | `models/bp1_customer_intent_classification/bp1_champion_pipeline.joblib` | logistic_regression | 2,965,623 bytes | Fresh-refit accuracy 0.822403, reload diff 0.0 |
| BP2 | `models/bp2_customer_friction_classification/bp2_champion_bundle.joblib` | XGBoost | 452,792 bytes | Fresh-refit accuracy 0.755773, reload diff 0.0 |
| BP3 | `models/bp3_complaint_escalation_prediction/bp3_champion_bundle.joblib` | XGBoost | 138,541 bytes | Fresh-refit PR-AUC 0.349569, reload diff 0.0 |
| BP4 | `models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet` | N/A — deterministic aggregation, not a trained model | 376,638 bytes | 37,160 rows, 0 duplicate keys, round-trips against the source CSV exactly |
| BP5 | *(none)* | N/A — association study, no classifier to persist | — | Association statistics are recomputed fresh from the Gold layer on every run, by design |
| BP6 | *(none)* | N/A — retrieval + live Google Gemini call, no local model | — | Grounding is verified per-run (real evidence IDs cited, 0 grounding failures) |
| BP7 | *(none)* | N/A — deterministic weighted-rule engine, no trained model | — | Champion weights re-derived live at full precision every run, never cached |
| BP8 | `powerbi/gold_tables/*.parquet` (11 tables) | N/A — Gold-layer aggregation, not a decision model | 2KB-260KB each | Row counts and schema cross-checked against every upstream BP's own Gold table |

Every `.joblib`/`.pkl`/`.onnx`/`.parquet` model artifact is excluded from version control (`.gitignore`) —
the model registry above documents what the owner's own real run produces locally, not what's committed
here. `src/deployment/*_readiness_verdict.py` (per BP) is what actually audits this table's claims against
the real filesystem — SHA-256 hash checks, a real reload, and a re-run of that BP's own test suite as a
subprocess.
