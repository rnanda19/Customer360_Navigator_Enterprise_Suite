# MLflow Deployment Guide (Phase D)

**Status: real, locally verified with a local sqlite-backed store. A real external MLflow server
was not stood up as part of this phase (see §4's honest disclosure).**

## 1. What runs today

This project's MLflow integration (`src/mlops/tracking.py`) uses a **local, file/sqlite-backed**
tracking store by default: `sqlite:///<repo_root>/mlruns/mlflow.db`, with artifacts written to
`<repo_root>/mlruns/artifacts/`. No external MLflow server, managed service, or database is
required to reproduce everything described in `MLOPS_TEST_REPORT.md`. This matches the project's
existing "no managed external service claimed" posture — the same posture `SECRETS_MANAGEMENT.md`
and `MLOPS_OBSERVABILITY.md` already disclose for their own respective pieces.

`mlruns/` is gitignored (see `.gitignore`'s Phase D addition) — it is a machine-local
training/registration output, exactly like `models/**/*.joblib` already was before this phase.

## 2. Installing mlflow

```bash
pip install mlflow>=2.9   # or: pip install -r requirements.txt
```

Tested in this delivery against the exact version `mlflow==3.17.2` (installed locally; see
`MLOPS_TEST_REPORT.md` §1 for the full real `capture_software_versions()` output of that run).

## 3. Running the real BP1 training + registration script

```bash
python scripts/mlops/bp1_train_and_register.py --data-dir "<path to the real BANKING77 CSVs>"
```

The real BANKING77 CSVs (`banking77_train.csv`, `banking77_test.csv`) are **not** committed to
this repository (`data/.gitignore` — unchanged by Phase D) and must be supplied from wherever
this project's other BP1/BP2 notebooks already source them.

## 4. Pointing this at a real MLflow server (not done in this phase — disclosed, not implemented)

`tracking.get_tracking_uri()` reads `MLFLOW_TRACKING_URI` from the environment **first**, before
falling back to the local sqlite default:

```bash
export MLFLOW_TRACKING_URI="https://your-mlflow-server.example.com"
```

This is the real, tested override point (`tests/mlops/test_tracking.py::
test_get_tracking_uri_respects_env_override`) — but no real external MLflow server was deployed
or connected to as part of this Phase D delivery. This is a genuine gap, named here rather than
implied as done.

## 5. Credential sourcing — reusing the existing Vault PoC (documented pattern, not live-wired)

Phase D's Step 2.9 requirement was to "reuse the existing secrets-management architecture" for
MLflow/registry credentials. This project's existing architecture is the real, CI-verified
HashiCorp Vault dev-mode proof-of-concept at `docs/secrets_management_demo/` (verified by
`.github/workflows/vault-verify.yml`), which `SECRETS_MANAGEMENT.md` already discloses is **not**
wired into any live service yet.

Phase D does not change that disclosure's truth value. What Phase D adds is the **same
environment-variable-first pattern** this project would use to wire Vault in: a real MLflow
tracking-server deployment would store its basic-auth credentials or a bearer token in Vault,
inject them into the calling process's environment at run time (exactly how
`docs/secrets_management_demo/vault_dev_example.sh` already demonstrates reading a real secret
back out of dev-mode Vault), and `tracking.get_tracking_uri()`'s env-var-first check is the real
code path that would pick up a `MLFLOW_TRACKING_URI` containing embedded credentials or set
alongside a separate `MLFLOW_TRACKING_TOKEN` without any code change. This is a documented
integration **point**, not a claim that MLflow and Vault are connected today.

## 6. Local artifact and audit-record protection

`governance/*.jsonl` (the governance and audit logs) are plain, human-readable, append-only files
under normal filesystem permissions — no additional access control was added in this phase beyond
what the repository's existing filesystem/git permissions already provide. A production
deployment would place these behind the same access controls as the rest of this project's
governed artifacts; this phase does not claim that has been done.
