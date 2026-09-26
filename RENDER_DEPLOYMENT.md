# Deploying BP7 as a real public API (Render.com free tier)

This is a real deployment guide for `src/services/bp7_decision_engine_service.py`, BP7's
Customer Navigator Decision Engine. Claude cannot create the Render account or click "Deploy"
for you (account creation and any external service configuration are outside Claude's
execution boundary on this project) — this document is the exact, real set of steps to do it
yourself. Everything below reflects the actual Dockerfile, compose file, and service code
already in this repo; nothing here is aspirational.

## Why Render, and why the free tier

Confirmed live (WebSearch + WebFetch, September 2026) against Render's own published free-tier
terms:

- No credit card required to deploy a free web service.
- 512 MB RAM / 0.1 CPU per free instance.
- A free web service spins down after 15 minutes with no inbound traffic, and takes roughly
  60 seconds to wake back up on the next request (a real cold-start cost — disclosed here, not
  hidden).
- Render can build directly from a Dockerfile in a GitHub repo, which is exactly how this
  service already ships (`src/services/docker/bp7_decision_engine_service/Dockerfile`).

This is an honest fit for a single-instance demo/portfolio deployment of a read-only lookup
service — not a claim that free-tier Render is production-grade for a real financial
institution's traffic. The in-memory rate limiter and `/metrics` endpoint added in this
hardening pass are both explicitly disclosed as per-process/non-distributed for exactly this
reason (see the service module's own docstring).

## What this deploys

BP7 is a read-only lookup service over a real, persisted, ~540MB/1,048,575-row CSV
(`gate5_full_population_decision_records.csv`) baked into the Docker image at build time (see
the Dockerfile's own header for why the image is intentionally large). It makes zero external
network calls of its own.

## Fastest path: the Render Blueprint (`render.yaml`)

This repo now ships a real [Render Blueprint](https://render.com/docs/blueprint-spec)
(`render.yaml` at the repo root) that describes this exact Dockerfile/health-check/env-var setup
to Render, so most of the manual console steps below are pre-filled for you:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rnanda19/Customer360_Navigator_Enterprise_Suite/tree/main)

Clicking it takes you to Render, where **you** sign in or create an account, review the one
service Render found in `render.yaml`, and approve it — Claude cannot do any part of that step
for you (account creation and clicking "Approve" are both outside Claude's execution boundary on
this project). The only thing you still have to type in yourself is your real `C360_API_KEY`
(and optionally `C360_GIT_COMMIT`) — `render.yaml` deliberately leaves those blank
(`sync: false`) rather than storing a secret in this repo, so Render's own dashboard prompts you
for them during that same approval flow. Everything else (Dockerfile path, build context, health
check path, free-tier plan) is already set correctly in `render.yaml` — verify it matches the
manual steps below if you ever edit either file, since they describe the same service twice.

If the Blueprint flow ever fails to sync (it happens — see
[Render's own community reports](https://community.render.com/t/blueprint-sync-fails-with-no-error-messages/3707)),
the fully manual path below configures the identical service by hand.

## One-time setup (manual console path)

1. **Confirm the real artifacts exist and are committed.** Render builds from your GitHub repo,
   so `notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_full_population_decision_records.csv`
   and `gate5_decision_layer_summary.json` must actually be present and pushed to `main` — the
   Dockerfile's `COPY` step fails the build otherwise (by design — see its header).
2. **Generate a real API key** for this deployment (do not reuse a local dev value):
   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. **Create a Render account** at render.com (no credit card needed for the free path).
4. **New + → Web Service**, then connect the `Customer360_Navigator_Enterprise_Suite` GitHub
   repo (grant Render's GitHub App access to it if this is the first service you're deploying
   from this repo).
5. **Configure the service:**
   - **Name:** `c360-bp7-decision-engine` (or your own choice).
   - **Region:** whichever is closest to you.
   - **Branch:** `main`.
   - **Runtime:** Docker.
   - **Dockerfile path:** `src/services/docker/bp7_decision_engine_service/Dockerfile`
   - **Docker build context:** `.` (the repo root — this matches the Dockerfile's own header
     comment; Render's "Docker Build Context Directory" field must be the repo root, not the
     Dockerfile's own directory, or the `COPY src/ ./src/` step will fail to find its source).
   - **Instance type:** Free.
6. **Environment variables** (Render's dashboard → Environment tab):
   - `C360_API_KEY` = the real value you generated in step 2. **Required** — the service refuses
     every protected endpoint with 503 until this is set (see `SECURITY.md`).
   - `C360_GIT_COMMIT` = the short commit SHA you are deploying (`git rev-parse --short HEAD`
     locally before you push). Optional but recommended: the built container has no `.git`
     directory (the Dockerfile never copies it), so without this `GET /version` honestly reports
     `git_commit: null` rather than a guessed value.
   - `C360_RATE_LIMIT_PER_MINUTE` = optional, defaults to `120` if unset. Lower it for a public
     demo deployment if you want tighter protection; `0` disables the limiter entirely.
7. **Health check path:** `/health` (matches the Dockerfile's own `HEALTHCHECK` and Render's
   health-check field) — Render uses this to know the instance is ready and to auto-restart it
   if it stops responding.
8. **Create Web Service.** The first build bakes in the ~540MB CSV, so expect the initial build
   to take noticeably longer than a typical small Python service — this is expected, not a
   failure.

## Verifying the real deployment

Once Render reports the service is live, run these against your real Render URL
(`https://<your-service-name>.onrender.com`) — the first request may take up to ~60 seconds if
the free instance had spun down:

```bash
# Public, no key needed
curl https://<your-service-name>.onrender.com/health
curl https://<your-service-name>.onrender.com/version

# Protected - needs your real C360_API_KEY
curl -H "X-API-Key: <your-real-key>" https://<your-service-name>.onrender.com/decide/self-test
curl -H "X-API-Key: <your-real-key>" https://<your-service-name>.onrender.com/model-info
curl -H "X-API-Key: <your-real-key>" -X POST \
  -H "Content-Type: application/json" \
  -d '{"complaint_ids": [<a real Complaint ID from your own dataset>]}' \
  https://<your-service-name>.onrender.com/score
```

A genuine `/decide/self-test` response with `"all_checks_passed": true` and
`"real_external_api_call_made": false` on your real, deployed instance is the honest proof this
is the same real lookup service running in production, not a claim taken on faith.

## What this deployment does NOT give you

- **No distributed rate limiting or metrics.** Both are real but explicitly in-memory,
  per-process (disclosed in `/metrics`' own response and the service module's docstring) — they
  reset on every cold start/restart and are not meaningful if you ever scale to more than one
  instance.
- **No autoscaling on the free tier**, and a real ~60-second cold start after 15 minutes idle.
- **No CI/CD gate on this Render service specifically** — Render redeploys on every push to
  `main` by default; this repo's own GitHub Actions workflows (CI, lint, CodeQL, Docker
  verification) are a separate, already-existing safety net that runs independently of Render.
