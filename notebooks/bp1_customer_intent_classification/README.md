# BP1 - Customer Intent Classification - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end.

Target: 77-class Banking77 intent taxonomy (secondary: 9-bucket `common_taxonomy_bucket`), TF-IDF text features over Banking77's 13,083 rows.

Champion: **logistic_regression** (6-model benchmark). Held-out test accuracy **0.8224**, F1-macro **0.8221**, 77-class ROC-AUC (OVR macro) **0.9933**.

Gate order: G1 Business Understanding -> G2 Data Integration/Taxonomy Mapping -> G3 Model Benchmark -> G4 Statistical Validation & Explainability -> G5 Decision Layer & Reporting -> G6 Productization/Monitoring/Governance -> Executive Rollup. A standalone `model_persistence.ipynb` (hardening pass) refits and persists the champion for serving.
