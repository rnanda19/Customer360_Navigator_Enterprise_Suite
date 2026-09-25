# BP2 - Customer Friction Classification - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end.

Target: 4-class ordinal friction severity, derived from `Company response to consumer` + `Timely response?` (structured CFPB fields only, no free text).

Champion: **xgboost** (6-model benchmark; CatBoost dropped after a real Gate-3 failure). Held-out test F1-macro **0.4559** under a real 152:1 class imbalance, accuracy **0.755773**.

Same G1-G6 + Executive Rollup gate order as BP1. A standalone `model_persistence.ipynb` (hardening pass) refits and persists the champion bundle (a keyed dict, not a bare sklearn Pipeline - the company-frequency encoder lives outside the Pipeline abstraction by design).
