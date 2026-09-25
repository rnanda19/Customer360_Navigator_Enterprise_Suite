# github_repo/ - staged GitHub packaging copy

This folder mirrors what actually gets pushed to the public GitHub repository. It is intentionally separate
from the working folders one level up (notebooks/, src/, tests/, etc.) for one specific, real reason:

STANDING LESSON (AMEX RiskIQ GitHub push): `git` cannot run inside a device-mounted folder - its object-store
bookkeeping needs a real `unlink`, which the mount blocks (`unable to unlink tmp_obj...`, `index.lock` errors).
This folder - and this whole Documents path - is a mounted folder, so `git init` / `git add` / `git commit`
must NEVER be run here.

## The actual push workflow (proven on AMEX and Home Credit RiskIQ; repeated 2026-09-25 for this repo)
1. Finished, real-run-confirmed BP content is copied/synced from the working folders into this `github_repo/`
   mirror (README, docs, notebooks, src, tests, reports, configs, .github/workflows - never data/raw,
   data/processed, model binaries, or logs/, per .gitignore; anything over 3MB is also excluded by convention
   to keep the repo lean - the one real exception worth knowing about is `notebooks/bp7_.../artifacts/
   gate5_full_population_decision_records.csv`, a real ~543MB full-population CSV that is deliberately never
   committed).
2. This folder's content is staged into the Claude session's cloud container (not this device, and not
   GitHub) as a tarball, extracted there, and `git init` + the initial commit happen in that container's own
   filesystem - the mount restriction above does not apply there.
3. **Claude has no GitHub API access or Personal Access Token in this project, by design - it never pushes
   to GitHub itself.** The repository must be created on GitHub.com and the actual `git remote add` + `git
   push` run by the project owner, either from this device (a normal, non-mounted local clone/init - never
   from inside this Documents mount) or by downloading the committed tree Claude prepared. If the owner wants
   Claude to run the push from its own cloud container instead, that requires the owner to supply a Personal
   Access Token with the `repo` scope directly in that session (never written to a file on this device) -
   an explicit, one-time decision, not a default.
4. Nothing above ever writes outside this Documents project folder on this device.

## Repo naming
Final: **`Customer360_Navigator_Enterprise_Suite`** - underscores, matching the naming convention of this
account's sibling portfolio repos (`AMEX_RiskIQ_Enterprise_Credit_Risk_Platform`,
`Home_Credit_RiskIQ_Enterprise_Suite`, `FraudShield_Enterprise_Risk_Intelligence_Platform`) and the local
project folder's own existing name - not the earlier hyphenated suggestion, which was written before those
sibling repos' real naming pattern was confirmed.

## What is excluded from the push (mirrors the root .gitignore)
Raw/processed CFPB and BANKING77 data, trained model binaries (.joblib/.pkl/.onnx), logs/, __pycache__/,
notebook checkpoints, and anything under configs/ that ever holds a credential or API key.
