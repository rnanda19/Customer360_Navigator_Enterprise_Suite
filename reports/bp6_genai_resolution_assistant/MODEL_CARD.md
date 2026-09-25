# Model Card — BP6 GenAI Resolution Assistant

*Generated 2026-09-24T16:45:52.155603+00:00 by `bp6_genai_resolution_assistant_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP6 Gates 1-5's own real runs on this machine plus
this gate's own real FastAPI self-test. No field below was authored freeform or by a generative
model (project zero-fabrication rule) - the one real GenAI-authored field anywhere in this BP,
`generated_recommendation_text`, is quoted verbatim from Gate 5's own real, saved artifact, never
paraphrased.*

## Model Details
- **Nature of this BP**: a real-time, retrieval + grounded-generation resolution-recommendation
  layer over BP1-BP5's own real Gate 7 outputs - **not** a trained classifier and **not** a
  population-level statistical-association BP (contrast BP5, which persists no model and no
  service; BP6 persists no model either, but per Master Plan paragraph 205, DOES require and ship
  a real, runnable FastAPI service - see Governance below).
- **Retrieval champion** (Gate 3, independently reproduced at Gate 4):
  `taxonomy_bucket_match`, real coverage
  0.3333 (runner-up
  `raw_string_match`, coverage
  0.0000). Gate 4's own independent reproduction:
  0.3333
  (`coverage_reproduces_exactly=True`), bootstrap
  95% CI [0.0000,
  0.6667] over
  3 real cross-corpus-hit buckets.
- **Generation model** (Gate 5's own real call, re-confirmed identical by this gate's own real
  self-test): `gemini-3.5-flash`, real
  input_tokens=1032,
  output_tokens=113,
  finish_reason='FinishReason.STOP' (never `MAX_TOKENS` - see Known
  Limitations for the real, fixed thinking-token truncation issue this gate structurally guards
  against on every run).

## Intended Use
- Drafts a short (2-4 sentence), evidence-cited, human-reviewed next-action recommendation for a
  customer-service team member handling one real customer message - never applied, sent, or
  finalized automatically (`approval_status` is always `PENDING_HUMAN_REVIEW`,
  `auto_applied` is always `False`, enforced structurally at Gate 5 and re-verified live by this
  gate's own Section 4).
- Out of scope: this BP never asserts a fact that is not one of the real, cited evidence items
  retrieved from BP1-BP5's own real Gate 7 outputs (Master Plan paragraph 117's own "deterministic
  template around GenAI" architecture) - it is not a general-purpose chat assistant.

## Training Data
BP6 fits no model and has no training data. Its real inputs at generation time are: (1) BP1-BP5's
own real Gate 7 executive rollup manifests (the evidence bundle -
28 real citation items available at Gate 5's
own run), and (2) one real, PII-screened customer message drawn from Gate 2's own real,
already-screened corpus (13083 rows screened,
0 flagged across
email, phone, ssn_like, card_like categories).

## Evaluation Data & Results
- **Retrieval strategy** (Gate 3/4): see Model Details above - a coverage metric over real
  taxonomy buckets, not a supervised-classifier metric.
- **Generation quality gates** (Gate 5, re-verified on the currently saved real artifact by this
  gate's own Section 4): citation_check_passed=True, udaap_check_passed=True,
  finish_reason != "MAX_TOKENS", nist_ai_rmf_risk_category="MEDIUM" (never HIGH or LOW by this
  project's own design - see Ethical Considerations).
- **Real citation usage**: 4 of
  28 available real evidence items cited in
  Gate 5's own real recommendation (reuse ratio 0.1429).

## Governance — Master Plan Paragraph 205 (BP6/BP7-specific requirement)
- **MODEL_CARD.md / CHANGELOG.md**: this file and its sibling, generated deterministically by this
  gate from Gates 1-5's own real recorded values.
- **Runnable FastAPI service**: `src/services/bp6_resolution_service.py` (`/`, `/health`,
  `/resolve`, `/resolve/self-test`) - Docker packaging at
  `src/services/docker/bp6_resolution_service/`.
- **Live self-test proving API output matches direct computation**: run for real by this gate
  (Section 9) - exactly ONE real Gemini call, the service-composed artifact and an independently,
  directly-computed artifact derived from that SAME real response compared field-for-field:
  `identical=True`. See the service module's own docstring for why this
  - not two live calls diffed for byte-identical prose - is the honest proof.

## Ethical Considerations & Governance
- **UDAAP** and **NIST AI RMF** are BP6's real, applicable compliance touchpoints (Master Plan
  Section 9). Gate 5's own real run: udaap_check_passed=True,
  nist_ai_rmf_risk_category="MEDIUM" (this project's
  own documented floor for a live customer-facing GenAI call is MEDIUM - never LOW; any mitigation
  failure is HIGH, and this gate's Section 4 refuses to proceed if the currently saved artifact is
  ever HIGH).
- **GLBA PII masking**: Gate 2's own real screen re-confirmed clean
  (0/13083 rows flagged)
  before any text reached a GenAI prompt.
- **Human-in-the-loop**: every real recommendation is `PENDING_HUMAN_REVIEW`, never auto-applied -
  re-verified live by this gate, not merely assumed from Gate 5's own design intent.

## Known Limitations (detected LIVE from real Gate 3/4/5 artifacts, not from memory)
- **Real, fixed thinking-token truncation issue** (documented upstream at
  `github.com/googleapis/python-genai` issue #782): Gemini's "thinking" models can silently
  consume most or all of `max_output_tokens` on invisible reasoning tokens before writing any
  visible answer text. Fixed in `src/genai/bp6_grounded_generation.py` by disabling thinking
  (`thinking_config=ThinkingConfig(thinking_budget=0)`) and gating on `finish_reason`, both
  structurally re-verified as still in effect by this gate's own Section 4 on every run.
- **Low citation-reuse ratio flag**: True (real ratio
  0.1429) - a real, disclosed signal that the curated evidence
  bundle is larger than what a single recommendation draws on; not an error.
- **Short generated-text flag**: False
  (real length 492 chars) - Gate 5's real
  output remains within its own instructed 2-4 sentence range and passed `finish_reason == "STOP"`
  cleanly; surfaced here only as a soft governance signal, distinct from the hard MAX_TOKENS guard.
- **No persisted model bundle and no static index** (contrast BP1-4's joblib bundles and BP4's
  Parquet index): every real `/resolve` call performs a fresh, live retrieval + generation round
  trip - there is nothing to version beyond the service code and prompt template themselves.

## Testing & Reproducibility (this Gate 6 run)
- **Full project pytest suite**: `[33m================ [32m363 passed[0m, [33m[1m6 skipped[0m, [33m[1m182 warnings[0m[33m in 21.06s[0m[33m ================[0m` (all passed: True)
- **Static notebook-syntax audit**: returncode=0 (all passed: True)
- **Real FastAPI self-test**: identical=True
- BP6's own first-ever test coverage, delivered alongside this gate:
  `tests/bp6_genai_resolution_assistant/test_bp6_grounded_generation.py` (unit coverage of every
  pure real function in `src/genai/bp6_grounded_generation.py`),
  `tests/bp6_genai_resolution_assistant/test_gate_artifacts.py` (schema/cross-artifact consistency
  checks for Gates 1-6's real saved output), and
  `tests/services/test_bp6_resolution_service.py` (the FastAPI service's own CI-safe suite, every
  Gemini call mocked at the `google.genai.Client` boundary - never a real network call in CI).

## [Gate 1] Business Understanding & Policy — 2026-09-24T15:44:03.886329+00:00
- Real GenAI call first occurs at Gate 5
  (this gate makes zero external calls, per Gate 1's own policy)
