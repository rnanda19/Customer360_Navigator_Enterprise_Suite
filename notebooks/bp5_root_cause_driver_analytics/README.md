# BP5 - Root-Cause & Driver Analytics - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end.

CFPB-only (no Banking77). Two real target outcomes: `outcome_1_intervention_required` (reused from BP3) and `outcome_2_timely_response_failure` (new). **Association-only, never causal** - every output is disclosed as a statistical association (Cramer's V, chi-square, closed-form log-odds-ratio + Wald CI), not a causal driver claim.

Champion methodology: univariate logistic association per candidate field, cross-checked against `statsmodels`. No SHAP-eligible black-box model - explainability is the association statistics themselves.

ECOA/Reg B: NOT_APPLICABLE for this BP's own modeling (association study, not a decision model) - UDAAP scanning applies instead (quote-masked, per-sentence scan for unfair/deceptive/abusive language in any narrative excerpt, a pattern later reused by BP6).
