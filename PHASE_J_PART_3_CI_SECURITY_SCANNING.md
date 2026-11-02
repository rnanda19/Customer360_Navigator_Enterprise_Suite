# Phase J (Part 3): Secret Scanning, SBOM Generation, Container Vulnerability Scanning

## What this closes

The remaining Phase I (security) items from the Master Engineering Directive that
Part 1 (Dependabot triage) and Part 2 (secrets-provider abstraction) did not cover:
secret-scanning in CI, SBOM generation, and container vulnerability scanning.
Dependency vulnerability scanning for Python packages is already covered by the
existing Dependabot configuration and this session's own Part 1 triage; this slice
adds the three pieces that had no CI presence at all.

## What was added

- **`.github/workflows/secrets-scan.yml` (new)** — runs `gitleaks/gitleaks-action@v3.0.0`
  on every push/PR with `fetch-depth: 0` (full commit history, not just the current
  checkout). This repository is owned by a personal GitHub account, not an
  organization, so per gitleaks-action's own published licensing terms no
  `GITLEAKS_LICENSE` secret is required or referenced.
- **`.github/workflows/sbom.yml` (new)** — generates a CycloneDX 1.6 Software Bill
  of Materials from `requirements.txt` using `cyclonedx-bom==7.6.0` (pinned exactly,
  matching this project's own existing pinning convention), writes a short summary
  to the job's step summary, and uploads the SBOM as a 90-day build artifact via
  `actions/upload-artifact@v4` rather than committing it to the repo (a committed
  SBOM would silently drift from the real dependency set on the next
  `requirements.txt` change with nothing to catch it).
- **`.github/workflows/docker-verify.yml` (modified)** — two new steps inserted
  into the existing `docker-validate` job, immediately after the step that builds
  all 8 service images and before the step that runs/health-checks them: installs
  Trivy (`v0.36.0`, via its official install script, pinned) and scans each of the
  8 already-built images for `CRITICAL`/`HIGH` severity vulnerabilities, writing a
  per-image report to the job's step summary.

## Design decisions

- **The Trivy step is a soft gate (`--exit-code 0`), not yet a hard gate.** This
  project already has an established precedent for exactly this situation —
  `code-quality.yml`'s mypy step is `|| true` with its real finding count disclosed
  to the step summary, explicitly because no real baseline had been observed yet
  and this project's own stated convention is to "disclose the real number, never
  invent a threshold." No container vulnerability scan has ever run against these
  images before this change, so there is no basis yet for a real pass/fail CVE
  count or severity threshold. This becomes a hard gate once a real baseline run
  has actually been observed and a deliberate threshold is chosen - not before.
- **Why these specific images.** The scan targets the exact 8 `ci-smoke`-tagged
  images the job already builds for its own build-mechanics and health-check
  steps - no new images are built solely for scanning. As that step's own existing
  comment discloses, these images contain placeholder (gitignored, zero-byte or
  stub) model/data artifacts, never the real trained models - so this scan proves
  the base image and installed OS/Python package layers, exactly matching what the
  rest of that job already proves and disclaims about these images.
- **Why a separate workflow file for gitleaks and SBOM, not an added job in
  `code-quality.yml`.** Matches this project's own established pattern (see
  `docker-verify.yml`'s and `code-quality.yml`'s own history comments: each was
  split out of `ci.yml` specifically so a failure in one reads as what it actually
  is - "Secret Scanning", "SBOM Generation", and "Docker Build & Run Verification"
  each now carry an honest, independent status badge instead of folding into a
  generic "CI" or "Lint & Format" result).
- **Action/tool versions used are real, current, verified releases** (not
  invented): `gitleaks/gitleaks-action@v3.0.0`, `aquasecurity/trivy-action`'s
  sibling CLI pinned at `v0.36.0` (the Action itself was considered and rejected
  in favor of a one-time binary install + a plain bash loop over 8 images, to
  avoid 8 duplicated Action blocks and to match this exact file's own existing
  `check_health()` bash-function style for repeated per-image operations), and
  `actions/upload-artifact@v4` (matching this project's existing major-version-only
  pinning convention for GitHub-authored Actions, e.g. `actions/checkout@v7`).

## Verification performed - and what could NOT be verified in this environment

- **SBOM generation was verified for real, end to end**, not just reviewed as
  YAML: `cyclonedx-bom==7.6.0` was installed in this environment and run against
  this repository's actual `requirements.txt`, producing a genuine CycloneDX 1.6
  document (`bomFormat: CycloneDX`, `specVersion: 1.6`, 45 real components parsed
  from the real file, e.g. `PyYAML>=6.0`). The workflow step runs the identical
  command.
- **The gitleaks and Trivy steps could NOT be run end-to-end in this environment**
  and this is disclosed plainly rather than glossed over: this environment has no
  Docker daemon (so the 8 images the Trivy step targets cannot be built here to
  scan), and gitleaks itself was not installed/run locally. Both workflow files'
  YAML was syntax-validated (`yaml.safe_load`), their action/tool versions were
  verified against each project's real current release pages (not assumed from
  training data), and their licensing terms (gitleaks) were read directly from
  the action's own documentation - but neither step's actual runtime behavior
  against this repository has been observed. That first real observation happens
  once this is pushed and GitHub's own CI infrastructure (which has Docker) runs
  it - the next CI run after this lands is the first real evidence of what either
  step actually finds.
- `git status` confirms only the 3 intended files changed (`docker-verify.yml`
  modified, `secrets-scan.yml` and `sbom.yml` new) - no source or test files
  touched by this slice.

## What this does NOT claim

- Does **not** claim the Trivy or gitleaks steps have ever actually run
  successfully against this repository - only that they are real, versioned,
  syntactically valid CI configuration, not yet observed in a real run.
- Does **not** claim any CVE count, severity, or "0 vulnerabilities" result for
  any of the 8 service images - no such scan has ever run yet, so no such number
  exists to report. The step summary produced by the first real CI run is the
  first honest source for that number.
- Does **not** turn the Trivy scan into a blocking gate - that is an intentional,
  disclosed deferral until a real baseline exists, following this project's own
  precedent for exactly this situation (mypy in `code-quality.yml`).
- Does **not** cover Python dependency vulnerability scanning as a new addition -
  Dependabot already covers that, and this session's own Part 1 already triaged
  its 19 real open PRs.
