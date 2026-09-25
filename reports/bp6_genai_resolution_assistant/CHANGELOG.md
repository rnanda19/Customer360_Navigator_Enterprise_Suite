# Changelog — BP6 GenAI Resolution Assistant

*Generated 2026-09-24T16:45:52.155603+00:00, deterministically, from real values recorded by BP6 Gates 1-6's own real
runs on this machine.*

## [Gate 6] Productization, Monitoring & Governance — 2026-09-24T16:45:52.155603+00:00
- Real full pytest suite: `[33m================ [32m363 passed[0m, [33m[1m6 skipped[0m, [33m[1m182 warnings[0m[33m in 21.06s[0m[33m ================[0m` (all passed: True)
- Real static notebook-syntax audit: returncode=0 (all passed: True)
- Real FastAPI self-test (Master Plan paragraph 205): identical=True
  (one real Gemini call, endpoint-composed vs. directly-computed artifacts compared field-for-field)
- MODEL_CARD.md and CHANGELOG.md generated deterministically from Gates 1-5's own real recorded
  values (this file)
- New test coverage delivered: `test_bp6_grounded_generation.py`, `test_gate_artifacts.py`,
  `tests/services/test_bp6_resolution_service.py`
- New production-style service delivered: `src/services/bp6_resolution_service.py` +
  `src/services/docker/bp6_resolution_service/` (Dockerfile, docker-compose.yml)
- Cross-gate consistency / regression-guard checks re-verified on the currently saved real
  artifacts (Section 4): the Gemini thinking-token truncation fix (issue #782) is confirmed still
  in effect (`finish_reason != "MAX_TOKENS"`), citation/UDAAP checks still pass, NIST risk category
  still MEDIUM, zero phantom citations referenced.
- Real open items surfaced live (never hardcoded): low_citation_reuse_ratio_detected=
  True, short_generated_recommendation_text_detected=
  False - see MODEL_CARD.md Known
  Limitations.

## [Gate 5] Decision / GenAI Layer & Reporting
- Real model: gemini-3.5-flash, input_tokens=1032,
  output_tokens=113, finish_reason='FinishReason.STOP'
- 4/28
  real evidence citations used; NIST AI RMF risk category:
  MEDIUM
- Provider pivoted from Anthropic Claude API to Google Gemini API (free tier) same day as original
  delivery; a real thinking-token truncation bug was found on the user's own first real run and
  fixed (see Gate 6's Known Limitations above)

## [Gate 4] Statistical Validation & Explainability
- Gate 3's recorded coverage independently reproduced: True
  (0.3333)
- Bootstrap 95% CI: [0.0000,
  0.6667] over 3
  real cross-corpus-hit buckets
- Leakage reconfirmed: True

## [Gate 3] Retrieval Strategy Benchmark & Champion Selection — 2026-09-24T15:44:05.107516+00:00
- Champion: taxonomy_bucket_match (coverage
  0.3333); runner-up: raw_string_match
  (coverage 0.0000)

## [Gate 2] PII Screening & Evidence Source Registry
- 13083 rows screened,
  0 flagged across
  email, phone, ssn_like, card_like

## [Gate 1] Business Understanding & Policy — 2026-09-24T15:44:03.886329+00:00
- BP6 scope, GenAI governance policy, and upstream-dependency status defined; real GenAI call
  first occurs at Gate 5
