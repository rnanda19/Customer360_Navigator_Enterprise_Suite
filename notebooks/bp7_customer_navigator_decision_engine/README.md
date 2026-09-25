# BP7 - Customer Navigator Decision Engine - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end - the suite's cross-BP triage layer over BP2/BP3/BP4.

Deterministic, transparent weighted-rule engine - no trained classifier, no GenAI call. Champion weighting scheme (`correlation_aware_plus_lr_diagnostic`, real Cramer's V=0.214 redundancy check between BP2/BP3 informed the weights): BP2 **0.222714**, BP3 **0.170774**, BP4 **0.606512**.

Full-population real scoring: **1,048,575 rows**. `recommended_action` breakdown: ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER 75.24% (automated cluster review, not per-complaint), STANDARD_QUEUE 23.16%, PRIORITY_QUEUE_REVIEW 1.60% (the only tier implying individual human review).

**Real, disclosed finding:** `adverse_impact_ratio = 0.908127` - passes the 0.8 four-fifths floor, not flagged. Carries forward and re-checks BP3's own disparate-impact question against this BP's own full-population output, independently.
