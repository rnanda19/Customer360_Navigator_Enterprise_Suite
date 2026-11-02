# MLOps Test Report (Phase D)

**Status: real, locally verified. Not yet committed or pushed — pending the repo owner's
authorization. Everything in this report was actually run on 2026-11-02 on the repo owner's own
machine via a connected-device session; nothing below is projected or assumed.**

## 1. Environment

```
python: 3.10.12
mlflow: 3.17.2
scikit-learn: 1.7.2
numpy: 2.2.6
pandas: 2.3.3
scipy: 1.15.3
joblib: 1.6.0
xgboost / lightgbm / catboost: not_installed in this environment (see §5)
git_sha at time of work: 75307b02701a3bbb11e8346c4725fe559e30942a
git_dirty: True (one pre-existing, unrelated LFS-smudge diff on BP7's Gate 5 artifact — not
           touched by this phase)
```

## 2. Real BP1 training, tracking, and registration

Command run:

```bash
python scripts/mlops/bp1_train_and_register.py --data-dir "<real BANKING77 source folder>"
```

Real output:

```
Loaded real BANKING77 data: train=10003 rows, test=3080 rows from <path>
Real fresh-refit held_out_test_accuracy = 0.822403 (fit took 2.4s)
Real fresh-refit held_out_test_f1_macro  = 0.821964
Historically recorded (configs/bp1_customer_intent_classification.yaml): accuracy=0.822403, f1_macro=0.8221
MLflow run_id = 39757d1f826347c7b107a42be3888910
Real joblib bundle saved (sha256=e93dba9b9049c30fbe0a410d81f945bcfae784bd83e3be8e61e2162110e914db, size=2936103 bytes)
Registered: customer360_bp1 version 1 (run_id=39757d1f826347c7b107a42be3888910)
```

**The real fresh-refit accuracy (0.822403) matches the historically recorded value in
`configs/bp1_customer_intent_classification.yaml` to 6 decimal places.** F1-macro (0.821964 real
vs. 0.8221 historically recorded) differs only at the 4th decimal, consistent with the historical
value being a rounded display figure rather than a different real result.

## 3. Real governance / champion-challenger / promotion / rejection / rollback demonstration

Three real model versions were registered against the real BANKING77 data:

| Version | Scenario | Real `held_out_test_accuracy` |
|---|---|---|
| 1 | Champion refit, `random_state=42` (default) | 0.822403 |
| 2 | Real challenger refit, `random_state=7` | 0.822403 (identical — convex optimization, single global optimum) |
| 3 | Real refit on a deliberately data-starved, stratified 231-row (3/class) subset | 0.397078 |

Sequence actually executed:

1. **v1 promoted** — governance passed (0.822403 ≥ 0.80 threshold); first-ever promotion (no
   prior champion to compare against); approved by `rnanda19`. `champion` alias → `1`.
2. **v3 promotion attempted and correctly blocked**:
   ```
   governance result: passed=False, reasons=[
     "Metric 'held_out_test_accuracy'=0.397... is below the governance minimum of 0.8.",
     "Metric 'held_out_test_f1_macro'=0.391... is below the governance minimum of 0.78."]
   CORRECTLY BLOCKED: Cannot promote bp1 v3: governance check failed: [...]
   ```
3. **v2 promoted** — governance passed, champion-challenger verdict passed (delta=+0.0000 vs.
   champion), approved by `rnanda19`. `champion` alias → `2`, `previous_champion` alias → `1`.
4. **Rollback to v1**, independently re-verified:
   ```
   rollback result: {'rolled_back_to_version': '1', 'rolled_back_from_version': '2', ...}
   champion alias after rollback: '1'   <-- confirmed by a FRESH registry query, not by trusting
                                             rollback()'s own return value
   ROLLBACK INDEPENDENTLY VERIFIED: champion alias == '1'
   ```
5. **Real smoke prediction from the rolled-back version's own MLflow-logged artifact** (freshly
   downloaded via `mlflow.artifacts.download_artifacts()`, not a locally cached file):
   ```
   Real smoke prediction: ['card_arrival'] confidence= 0.5034
   ```
   for the input "I have not received my new card yet, what should I do?" — a correct, sensible
   prediction for BANKING77's `card_arrival` intent class.

**A real bug was found and fixed during this testing, not before it**: MLflow 3.17.2's
`ModelVersion.version` attribute is an `int`, not a `str` as the first draft of
`src/mlops/registry.py` assumed. This caused a real, reproducible rollback-verification failure
(`AssertionError: ROLLBACK VERIFICATION FAILED: got 1` compared against the string `"1"`) the
first time it was run. Root cause confirmed directly (`type(v.version)` → `<class 'int'>`), fixed
by introducing `registry.AliasedVersion`, a small immutable wrapper that normalizes every version
to `str` before returning it to any caller — `ModelVersion.version` has no setter in this MLflow
version, so the fix could not simply mutate the existing object. Re-run and confirmed fixed.

A second real bug (also self-caught): `promotion.py`'s calls to `audit_log.record_event()` did
not pass `log_path` explicitly, so they always used that function's own default parameter — bound
once at `audit_log.py`'s import time — rather than respecting `monkeypatch.setattr(audit_log,
"AUDIT_LOG_PATH", ...)` in tests. This silently wrote real promotion/rollback test events into
the real repo-root `governance/audit_log.jsonl` during test development. Found via the test suite
itself (`test_successful_promotion_sets_champion_alias_and_records_audit_entry` and
`test_rollback_actually_restores_the_previous_champion_verified_by_requery` both failed on
`assert len(entries) == 1` / `assert False`). Fixed by resolving `audit_log.AUDIT_LOG_PATH`
dynamically inside each function body via a new `audit_log_path` parameter, and the accidental
test-pollution entries were identified and removed from the real log by `bp_id` filter.

## 4. Real unit test suite (Phase D's own modules)

```
python3 -m pytest tests/mlops/ tests/monitoring/test_prediction_monitor.py -v
...
72 passed in ~75-90s
```

Breakdown: `test_tracking.py` (13), `test_governance.py` (9), `test_champion_challenger.py` (14),
`test_audit_log.py` (6), `test_registry.py` (12), `test_promotion.py` (16, across a real,
isolated, temp-sqlite MLflow store per test, fitting a real `LogisticRegression` on synthetic
data), `tests/monitoring/test_prediction_monitor.py` (8). Every test is a real assertion against
real computed output — no mocked business logic.

## 5. Full project regression

```
python3 -m pytest tests/ -q
...
17 failed, 692 passed, 9 skipped in ~108s
```

**718 total collected = the project's pre-existing 646 + Phase D's 72 new tests.** All 17
failures are `ModuleNotFoundError` for `catboost`, `xgboost`, `lightgbm`, and `statsmodels` —
packages this project's own `requirements.txt` already declares for BP1/2/3/5/7, but which are
**not installed in this particular device's Python environment**. This is a pre-existing
environment gap, confirmed unrelated to Phase D: `pip install xgboost lightgbm catboost` and,
separately, `pip install statsmodels` were both attempted during this phase and both failed with
`OSError: [Errno 28] No space left on device` inside this sandbox's isolated per-call writable
area (the host disk itself reports 4.0G free via `df -h`, so this is a sandbox-local quota, not a
real disk-full condition — and outside the scope of this phase to work around). **Zero of the 17
failures are in code Phase D touched or added; zero NEW failures were introduced.**

## 6. Lint, format, and security — full project

```
black --check src/ tests/        -> All done, 131 files unchanged
isort --check-only src/ tests/   -> clean (exit 0)
flake8 src/ tests/                -> clean (exit 0)
ruff check src/ tests/            -> All checks passed
bandit -c pyproject.toml -r src/  -> 0 findings (20 pre-existing #nosec-suppressed B603/B607
                                      entries project-wide, 2 of them newly added by Phase D for
                                      src/mlops/tracking.py's two `git` subprocess calls, using
                                      this project's own existing `# nosec B603 B607` convention)
```

Two real flake8/bandit issues were found and fixed during this phase (not before it): six
over-110-character lines in `scripts/mlops/bp1_train_and_register.py` /
`src/mlops/champion_challenger.py` / `src/mlops/promotion.py` (wrapped), one unused `import
mlflow` in `registry.py` (removed — that function only needs the `MlflowClient` instance, not the
`mlflow` module directly), one `E402` from an import placed after a helper function definition in
`promotion.py` (reordered), and two B607 "partial executable path" bandit findings for
`subprocess.run(["git", ...])` (suppressed with this project's own existing `# nosec B603 B607`
convention, matching `src/deployment/*_readiness_verdict.py` and
`src/services/bp7_decision_engine_service.py`'s identical precedent).

## 7. What was NOT run in this phase

- No real re-fit of BP2–BP8 (see `MLOPS_ARCHITECTURE.md` §3 for why).
- No Docker build/verification re-run specific to Phase D (Phase D added no Dockerfile changes;
  BP7's existing `docker-verify.yml` is untouched and was not re-run as part of this pass).
- No GitHub Actions run of the new `.github/workflows/mlops-verify.yml` — it has not been pushed.
  Its logic (`scripts/mlops/ci_demo.py`) **was** run and verified locally with real output (§3's
  mechanics, replayed against a synthetic model) before being wired into the workflow file.
- No real external MLflow server or Vault-MLflow credential wiring (see `MLFLOW_DEPLOYMENT_GUIDE.md` §4–5).
