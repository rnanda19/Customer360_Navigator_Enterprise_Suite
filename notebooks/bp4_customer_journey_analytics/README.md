# BP4 - Customer Journey / Issue-Cluster Analytics - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end.

No customer identifier exists in the real CFPB schema, so this BP is explicitly scoped as **event/issue journey analytics**, never longitudinal customer journey analytics (per the Master Plan's own instruction not to invent customer IDs). Two real units of analysis: (1) complaint-event journey keyed by `Complaint ID` (`response_lag_days`), and (2) issue-cluster journey keyed by (Company, Product, Sub-product, Issue, Sub-issue) - 37,160 real clusters, 41.85% recurring, covering 97.94% of all rows.

No supervised target - Gate 3 is a **Polars/DuckDB lazy-aggregation-pipeline benchmark** (5 candidates), not a classifier benchmark. Champion: **polars_lazy_streaming**, ~29.5x speedup over the pandas baseline (3.067s -> 0.104s).

A standalone `..._decision_artifact_persistence.ipynb` (hardening pass) persists Gate 5's cluster decision report as a served Parquet index (no trained model to persist - a real, disclosed design difference from BP1-3/5).
