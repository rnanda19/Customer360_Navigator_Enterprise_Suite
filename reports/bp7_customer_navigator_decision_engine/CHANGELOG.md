# Changelog — BP7 Customer Navigator Decision Engine

*Generated 2026-09-25T06:49:02.757522+00:00, deterministically, from real values recorded by BP7 Gates 1-6's own real
runs on this machine.*

## [Gate 6] Productization, Monitoring & Governance — 2026-09-25T06:49:02.757522+00:00
- Real full pytest suite: `[33m================ [32m410 passed[0m, [33m[1m3 skipped[0m, [33m[1m182 warnings[0m[33m in 13.74s[0m[33m ================[0m` (all passed: True)
- Real static notebook-syntax audit: returncode=0 (all passed: True)
- Real FastAPI self-test (Master Plan paragraph 205, adapted for BP7's no-external-API nature):
  all_checks_passed=True over
  100 real rows (contribution reconstruction, threshold
  consistency, recommended_action structural consistency, dual independent-read identity) - zero
  external network calls made anywhere
- MODEL_CARD.md and CHANGELOG.md generated deterministically from Gates 1-5's own real recorded
  values (this file)
- New test coverage delivered: `tests/services/test_bp7_decision_engine_service.py`,
  `tests/bp7_customer_navigator_decision_engine/test_gate_artifacts.py`
- New production-style service delivered: `src/services/bp7_decision_engine_service.py` +
  `src/services/docker/bp7_decision_engine_service/` (Dockerfile, docker-compose.yml)
- Cross-gate consistency / regression-guard checks re-verified on the currently saved real
  artifacts (Section 4): contribution reconstruction still exact, weight rederivation still
  matches config, Gate 3/Gate 5 champion rule scheme still agree, leakage still reconfirmed clean,
  disparate-impact four-fifths flag still False, genai_api_used still False.
- Two real bugs found and fixed during this gate's own pre-delivery sandbox testing (synthetic
  fixtures only, per this project's standing execution-boundary rule): a FastAPI route-ordering
  bug that shadowed `/decide/self-test`, and a self-test false-positive on a real, structurally-
  honest unscored row - see MODEL_CARD.md Known Limitations for both.
- `status` field left untouched (this project's own established BP7 convention: Gates 2-6 never
  touch it - owned exclusively by Gate 1's own front-matter writer).

## [Gate 5] Decision Layer & Reporting
- Real champion: correlation_aware_plus_lr_diagnostic, weights
  {'bp2': 0.2227139837335739, 'bp3': 0.17077431022015202, 'bp4': 0.606511706046274}, threshold
  0.5
- 1,048,575 real complaints scored, 100% coverage
- intervention_flag_rate=0.768415,
  bp3_agreement_rate=0.285865
- Disparate impact: adverse_impact_ratio=0.908127,
  flagged_four_fifths_rule=False
- No GenAI API used (genai_api_used=False)

## [Gate 4] Statistical Validation & Explainability
- Champion reproduced bit-exact: True
- Bootstrap 95% CI (intervention_flag_rate): [0.767609, 0.769243]
- Leakage reconfirmed clean: True

## [Gate 3] Decision-Rule-Scheme Benchmark & Champion Selection — 2026-09-25T06:12:43.121570+00:00
- Champion: correlation_aware_plus_lr_diagnostic (coverage
  100.0%, bp3_agreement_rate
  0.285865)

## [Gate 1] Business Understanding & Policy — 2026-09-25T06:12:08.692639+00:00
- BP7 scope, output-field definitions, and leakage rules defined; recommended_action policy:
  deterministic, reason-code-keyed lookup, never GenAI
