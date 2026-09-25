# Roadmap

## Done
- All 8 business problems (BP1-BP8): every gate real-run confirmed end to end.
- Suite-wide executive rollup (`00_suite_executive_rollup`) real-run confirmed.
- Full hardening pass: model persistence, FastAPI inference/decision services, deployment-readiness
  verdict modules, Docker packaging, and CI (lint, bandit, pytest, notebook-syntax, docker-compose-validate)
  across all 8 BPs.
- BP3's disparate-impact finding fully investigated (proxy-feature audit + 2 fairness-aware retraining
  candidates) and a final governance decision recorded.
- GitHub repository built and pushed live.

## Not yet started (disclosed, not silently skipped)
- **System architecture diagrams** — one suite-wide diagram (BP1-8) plus one per BP. Deliberately held
  for a dedicated pass rather than rushed alongside the repo build.
- **Live deployment** — every BP's FastAPI service is real, tested, and CI-validated via Docker Compose,
  but none has ever been run behind a live public endpoint. No target platform has been chosen yet.
- **PDF export for the suite-wide rollup** — currently soft-skipped (no LibreOffice/Word installed on the
  build machine); every other output format (HTML/DOCX/XLSX/PPTX) is real and complete.

## Explicitly out of scope
- A financial-impact / ROI section. Permanently banned project-wide — every number in this repository is
  either a real measured result or an explicitly labeled statistical estimate (a confidence interval,
  never a dollar-value extrapolation).
- A ninth "modeling problem" wrapping BP8. BP8 is a Gold-layer aggregation step, not a decision model,
  and is documented that way everywhere it appears.
- Auto-applying any BP6 GenAI recommendation. Every recommendation is generated for human review, not
  for automatic action — this is a design decision, not a missing feature.
