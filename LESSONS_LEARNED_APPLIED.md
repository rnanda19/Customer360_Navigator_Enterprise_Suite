# Lessons Learned - Applied From AMEX RiskIQ & Home Credit RiskIQ

Real bugs and real fixes from the two prior platform builds, consolidated into standing rules for every
notebook and src/ module in this project. Read this before writing BP1's first notebook.

## 1. Never infer a column's dtype or granularity from its name alone
AMEX Notebook 27 assumed a `_last`-suffixed column was numeric because of its name; it was a real categorical
status code (dtype 'CR'). Home Credit Notebook 34 assumed a file named "features" was per-statement raw data;
it was already aggregated to one row per customer. STANDING RULE: always verify dtype (`pd.api.types.is_numeric_dtype`)
and granularity (row count vs. expected entity count) against the actually-loaded data, every time, never from
a filename or column-name pattern.

## 2. Never let a display-rounded or independently-recomputed value feed downstream scoring
AMEX Notebook 28's deployed scorer read a CSV column that had been rounded to 5 decimal places for human
readability, then used that rounded value as a real scoring weight - across ~243 features the rounding error
compounded into real decision-boundary flips (7 of 91,783 real holdout customers). STANDING RULE: any value
consumed by downstream scoring/deployment code is saved at full float precision, never rounded, even in a
column someone might reuse later; the downstream notebook reads that saved value directly rather than
recomputing it from a fresh reload.

## 3. Match iteration order exactly when reconstructing a weighted sum
A saved CSV's row order (often sorted for display, e.g. by weight descending) is not safe to reuse for
re-deriving a float sum computed in a different order (e.g. alphabetical) upstream - floating-point addition is
not associative. STANDING RULE: if a standalone/deployed scorer reconstructs a sum from saved per-feature
values, it must replicate the original notebook's real iteration order explicitly (e.g. `sorted(features)`),
not the display order of the saved file.

## 4. A self-test must check every reachable real row, not one sample
A single-customer self-test can pass "by luck" if that customer isn't near a decision boundary - AMEX's Bug 2
only surfaced on the full ~92k-row real holdout, never on a 500-row fixture. STANDING RULE: every standalone-
scorer or API self-test checks ALL real rows it can reach and reports a magnitude (a diff column), not just a
pass/fail count - a boundary-tie vs. hard-mismatch classification is only trustworthy once backed by a printed
number.

## 5. Configure the hardware/thread ceiling before any heavy import, and call it
Home Credit's Notebook 02 computed a WARP thread ceiling but never actually called `os.environ[...] = ` before
polars/pandas/sklearn/xgboost/lightgbm/catboost were imported - no library ever saw the ceiling, and the real
run used ~20% CPU / ~50% RAM on an 8-core/16-thread/32GB machine. STANDING RULE: call
`performance_setup.configure_performance()` as the literal first executable step, before any heavy import.
Also drop any model with no real multi-core support (e.g. sklearn's GradientBoostingClassifier) from a
CPU-parallel benchmark set rather than letting it silently pin execution to one thread.

## 6. A stale __pycache__ can reintroduce an already-fixed bug
A corrected shared/ module still failed to import correctly because an old `.pyc` in `__pycache__/` had a
newer name but an older mtime than the fix. STANDING RULE: after delivering any src/ module change, check for
and truncate any stale `__pycache__/*.pyc` on the device before assuming the fix landed.

## 7. An un-imputed ratio fed into a raw numpy call can fail silently, not loudly
`np.percentile()` on a division result with an undefined denominator returns NaN without raising - the failure
only surfaces later, at an unrelated plotting call. STANDING RULE: any computed ratio gets an explicit
undefined-count check and exclusion (never a silent impute for a purely descriptive ratio), with a finiteness
assertion immediately after.

## 8. Fixture testing catches most bugs; only your real run catches the rest
Every bug above except #5 and #8's own lesson was caught only after a real run on real, full-size data, even
though fixture testing had already passed. STANDING RULE (already in the Master Execution Plan's Gap Register
#1 and Quality Gates): two checkpoints are mandatory for every BP - a schema-matched synthetic-fixture
execution, and your own real run reported back. Neither alone marks a BP complete.

## 9. git cannot run inside this mounted Documents folder
git's object-store bookkeeping needs real unlink, which a device-mounted (fuseblk) folder blocks - confirmed
on AMEX's GitHub push. STANDING RULE: the actual `git init`/`commit` never happens inside this folder. Content
meant for GitHub is staged in `github_repo/` here, then committed and pushed following the workflow documented
in `github_repo/README.md`.

## 10. A GitHub PAT with empty oauth-scopes authenticates but cannot push
A classic PAT can pass a basic `GET /user` check while still having no `repo` scope checked at creation,
causing a silent-looking 404 on `POST /user/repos`. STANDING RULE: verify the `x-oauth-scopes` response header
is non-empty and contains `repo` before assuming any PAT is usable.

## 11. An upward-only project-root walk fails when the kernel's cwd is a PARENT of the project folder
The first real run of `00_hardware_benchmark.ipynb` failed at `_find_project_root()` with
`RuntimeError: Could not resolve PROJECT_ROOT` even though the notebook file itself lives inside the project
tree. Root cause: the resolver only walked UPWARD from `Path.cwd()` (plus one hardcoded `parent.parent`
fallback) - it never checked whether the marker file was in a CHILD directory of cwd. Several common Jupyter
setups (e.g. VS Code's Jupyter extension, which by default runs the kernel with cwd set to the workspace root
rather than the notebook's own folder) put the kernel's cwd one or more levels ABOVE the project folder, which
an upward-only search can never find. STANDING RULE: every project-root resolver in this project (the inline
copy in each notebook, and `src/utils/performance_setup.py`'s `resolve_project_root()`) now does env-var
override -> bounded upward walk (8 levels) -> bounded downward search (depth <= 3, hidden dirs skipped) ->
raise with an actionable one-line `C360_PROJECT_ROOT` fix. Never assume the kernel's cwd is inside the project
tree just because the notebook file is.

## 12. A silently-hanging cell looks identical to a "no output printed" bug - fix both the symptom and the likely cause
Second real run of `00_hardware_benchmark.ipynb` (after Lesson #11's fix) reported "no outputs are printed
after rerun," with no error shown. Two candidate causes, both real and not mutually exclusive: (a) `print()`
output can be buffered by some Jupyter front-ends/execution modes and only flushed once a cell fully
completes, so a long-running cell can look completely silent even while executing correctly; (b) SECTION 3's
CPU-thread benchmark loop calls `sklearn.model_selection.cross_val_score(..., n_jobs=min(5, n_jobs))`, which by
default dispatches through joblib's process-based "loky" backend - on Windows this uses the `spawn` start
method, which re-imports the entry-point module in every child process; inside an interactive Jupyter kernel
(no `if __name__ == "__main__":` guard, no freezable script) this is a well-documented real hang vector with
zero error and zero further output. STANDING RULE: (1) every notebook in this project now overrides `print`
immediately after its imports with `functools.partial(builtins.print, flush=True)`, so every print appears the
instant it runs rather than only at cell completion - this turns any future hang into a visible "stopped after
line X" instead of total silence; (2) any `cross_val_score`/parallel `n_jobs>1` call inside a notebook (as
opposed to a guarded `.py` script) is wrapped in `joblib.parallel_backend("threading", n_jobs=...)` to avoid
Windows/Jupyter process-spawn hangs entirely, and is preceded by an explicit `"[BENCH] starting n_jobs=...`
progress print so partial progress is visible even if something still stalls. Never assume "no output" means
"nothing happened" - it can mean the cell is still running with buffered output, or genuinely hung on a
process-based parallel backend; the fix addresses both possibilities rather than guessing which one occurred.

## 13. psutil's cpu_freq() on Windows reports the nominal/base clock as BOTH current and max - not the real turbo range
Real run of `00_hardware_benchmark.ipynb` printed `CPU freq current/max (MHz): 2000.0 / 2000.0` on the user's
machine, but the CPU's actual rated range is 2.0-5.0 GHz (min-max turbo). Root cause: on Windows, psutil's
`cpu_freq()` reads `Win32_Processor` via WMI, which only exposes the nominal/base clock under both
`CurrentClockSpeed` and `MaxClockSpeed` - Windows does not reliably expose live turbo-boost frequency through
this API at all, so `current == max` here is an OS/library limitation, not a benchmark bug, and there is no
alternative stdlib/psutil call that recovers the real turbo max without a native perf-counter tool this
project does not depend on. STANDING RULE: never silently ship a suspicious-looking number as if it were
verified - `detect_hardware()` now flags `cpu_freq_windows_wmi_limitation: true` whenever `os == "Windows"`
and `current == max`, and the notebook prints an explicit `[LIMITATION]` line explaining the WMI cause and
pointing the user to their CPU's spec sheet or Task Manager for the real turbo range, rather than presenting
2000/2000 MHz as this machine's true operating range. This value is cosmetic only - it is never used in the
thread-count/CV-mode recommendation, which is based on logical core count, not clock speed.

## 14. A naive line count (wc -l) over-counts CSV rows when a quoted field contains an embedded newline
`01_data_acquisition_profiling.ipynb`'s first real run failed its
`banking77_total_row_count_matches_manifest` check: the real, Polars-parsed BANKING77 total was 13,083
rows, not the 13,100 documented in `RAW_DATA_MANIFEST.md`. Root cause: the manifest's original row counts
were produced by a naive line count, which counts newline characters - it has no concept of CSV quoting, so
a quoted `text` field containing a literal embedded newline (a multi-line pasted complaint/query, common in
free-text fields) is wrongly counted as 2+ lines instead of the 1 logical row it actually is. A real RFC 4180
CSV parser (Polars, used by every notebook in this project) correctly collapses each such field back into
one row: 13 rows in `banking77_train.csv` and 4 in `banking77_test.csv` had this property, exactly matching
the 17-row gap (13,100 - 13,083). The CFPB file was unaffected (its line count and real parse agree exactly),
so this class of bug is data-dependent, not universal. STANDING RULE: never determine a CSV file's row count
by any means other than a real CSV parser (`pl.scan_csv(...).select(pl.len()).collect()` or equivalent) -
`wc -l`/naive line-splitting is only safe for row *estimation*, never for a value used in a structural
integrity check or written into a data-lineage document as fact. `RAW_DATA_MANIFEST.md` Section 1 and
Finding 6 have been corrected to the real, Polars-verified counts (13,083 BANKING77 total, not 13,100), and
both `01_data_acquisition_profiling.ipynb` and the BP1 Gate 2 taxonomy-mapping notebook's structural checks
now assert against 13,083 rather than the stale figure - the BP1 Gate 2 notebook was corrected before its
own first real run, so this bug was caught before it could reproduce there too.

## 15. Static checks (ast.parse/pyflakes/nbformat.validate) do not catch real runtime API bugs - a schema-matched synthetic-fixture dry-run does
Before delivering BP1 Gate 3 (`..._g3_model_benchmark.ipynb`, a 6-model TF-IDF text-classification
benchmark), it was dry-run against a small synthetic fixture (fake text/category CSVs matching BANKING77's
real schema, a fake project tree with the real shared `src/` modules and real config files) in an isolated
sandbox - not the user's real machine, not real project data. This is checkpoint (a) of the project's own
two-checkpoint verification standard ("a real, schema-matched synthetic-fixture execution - not a syntax
check"), which earlier BP1 notebooks this session had skipped in favor of static checks alone. The dry-run
surfaced three real bugs that ast.parse/pyflakes/nbformat.validate all passed cleanly:
1. `polars.read_csv(...).to_pandas()` raises `ModuleNotFoundError: No module named 'pyarrow'` when pyarrow
   is not installed - a real risk on this project, since `hardware_benchmark_summary.json`'s own live
   library scan already found several `requirements.txt`-listed packages missing on this exact machine
   (duckdb, spacy, transformers, numba, shap). Fixed by loading the small (~13K-row) BANKING77 file with
   plain `pandas.read_csv` instead, where WARP's lazy-scan benefit does not apply anyway.
2. XGBoost's sklearn API (`XGBClassifier.fit`) raises `ValueError: Invalid classes inferred from unique
   values of y` on raw string class labels - unlike LogisticRegression/RandomForest/LightGBM/CatBoost,
   which all accept string labels natively, XGBoost requires contiguous integer labels `0..n_classes-1`.
   Fixed with a single shared `LabelEncoder` applied to every candidate model (not just XGBoost, for
   consistency), decoding back to real category names for all human-readable output.
3. `HistGradientBoostingClassifier.fit` raises `TypeError: Sparse data was passed for X, but dense data is
   required` on this environment's real installed scikit-learn version - unlike every other candidate, it
   does not accept the sparse TF-IDF matrix directly. Fixed with a `FunctionTransformer` densify step added
   to ONLY that one candidate's pipeline (bounded, transient memory cost - never persisted).
STANDING RULE: any notebook combining multiple ML/data libraries (not just single-library notebooks like
`00_hardware_benchmark.ipynb`) is dry-run against a small synthetic fixture - built in an isolated sandbox,
using the real shared `src/` modules and real config schemas, never the user's real machine or real project
data - before delivery, in addition to the existing ast.parse/pyflakes/nbformat.validate static checks. The
fixture run is also re-run a second time in place to confirm idempotency (config-file patches must not
duplicate or corrupt on re-run). This does not replace the user's own real run (checkpoint (b) still stands
- these three fixes are unconfirmed on the real BANKING77 data until reported back), but it catches exactly
the class of real API-usage bug that a syntax check cannot.

## Lesson #16 — BP1 Gate 4: two real bugs caught by synthetic-fixture dry-run + a standalone SHAP check (2026-09-22)

**Context**: Building BP1 Gate 4 (Statistical Validation & Explainability) — paired significance test
(champion vs runner-up on identical CV folds), bootstrap CI, 77-class one-vs-rest macro ROC-AUC, and SHAP
explainability. Verified per the standing methodology (Lesson #15): source audit, then a synthetic-fixture
dry-run in Claude's own isolated sandbox — never the user's real machine or data — before delivery.

**Bug 1 — undefined paired t-test on exactly-tied fold scores.** The fixture's champion and runner-up scored
an identical 1.0 on every CV fold, making the t-test's variance term zero; `scipy.stats.ttest_rel` returned
`t=nan, p=nan`. `nan` is not `None`, so a naive `is not None` check would have silently reported this as a
valid, passing result — and `json.dump` would have written an invalid `NaN` token into the output JSON. Fixed
by explicitly detecting `np.allclose(paired_diffs, 0.0)` before calling the test, recording `None` with a
plain-language reason ("these two candidates were indistinguishable at the fold level") instead of a NaN, and
rewriting the affected integrity check to verify the comparison *ran* (both fold-score arrays are full length)
rather than that it produced a non-null p-value — a `None` p-value from a genuine tie is a legitimate, honest
outcome, not a failure to be masked.

**Bug 2 — `shap.TreeExplainer.shap_values()` rejects sparse input.** Caught by a standalone check (the fixture
dry-run only exercises the champion `logistic_regression`, which uses `LinearExplainer`, not
`TreeExplainer`) — this environment's real installed `shap` version (0.51.0) raises a cryptic
`numpy._core._exceptions._UFuncInputCastingError` (an `isnan` dtype-casting failure, not a clear "sparse not
supported" message) when `TreeExplainer.shap_values()` is given a sparse TF-IDF matrix directly, for every
tree-based candidate (RandomForest/HistGradientBoosting/XGBoost/LightGBM/CatBoost), not just the one model
already known to need densifying for its own *fit*-time constraint (Lesson #15's `NEEDS_DENSE` set, which is
about `HistGradientBoostingClassifier.fit()`, a separate concern). Fixed by always densifying the small SHAP
sample (150 rows max) before calling `TreeExplainer`, regardless of `NEEDS_DENSE` membership — confirmed via a
standalone RandomForest + sparse-TF-IDF-shaped-matrix test outside the notebook, since the fixture's own
champion never exercises this branch. Documented as a residual, lower-confidence path: this branch is
code-reviewed and standalone-verified, not fixture-dry-run-verified end-to-end inside the notebook itself,
since Gate 3's real champion (logistic_regression) will use `LinearExplainer` on your actual data too.

**Standing practice reinforced**: when a synthetic fixture's own characteristics (e.g. a small dataset
producing exact ties, or a fixture champion that only exercises one of several code branches) can't exercise
every real code path, a standalone unit-level check of the unexercised branch is required before delivery —
not skipped on the assumption that "it probably works the same way."

## Lesson #17 - BP1 Gate 4 real run: environment-level numba/NumPy conflict, and a wrong-conda-env install (2026-09-22)

**Context**: Gate 4's real run on the user's machine failed at `import shap`, not from any bug in the notebook's
own code - a pure environment/dependency-version conflict.

**Bug found**: the installed `shap` package pulls in `numba` as a hard, unconditional import (inside
`shap/utils/_clustering.py`). The `numba` version already present in the user's `home_credit_env` predated NumPy
2.5 support and hard-checks for it at import time, raising `ImportError: Numba needs NumPy 2.4 or less. Got NumPy
2.5.` This is an environment fact, not something the generator script could have anticipated or coded around -
`shap`'s own dependency spec does not cap the numba version on Windows, so whichever numba happened to get
resolved at `pip install shap` time is what you get.

**Verified fix (not guessed - confirmed against real, dated release info before recommending it)**: NumPy 2.5
support landed in `numba` 0.67.0 (paired with `llvmlite` 0.49+), a real, current release. Upgrading numba/llvmlite
in place - rather than downgrading NumPy, which risks destabilizing xgboost/lightgbm/catboost/scikit-learn that
were already confirmed working against NumPy 2.5 via Gate 3's real run - is the narrow, low-blast-radius fix:
`pip install --upgrade numba llvmlite` (or pinned: `pip install "numba>=0.67" "llvmlite>=0.49"`).

**Second bug: the fix was first applied in the wrong conda environment.** The user ran the upgrade in `(base)`,
but the Jupyter kernel that runs the Customer360 notebooks lives in a separate environment (`home_credit_env`) -
confirmed from the original traceback's file paths (`C:\Anaconda3\envs\home_credit_env\Lib\site-packages\shap\...`).
`base` and `home_credit_env` are entirely separate `site-packages` trees; upgrading a package in one does nothing
for the other. The user's first `pip install` attempt also silently no-op'd for an unrelated reason: pasting a
bare package list (`psutil joblib scikit-learn ...`) with no `pip install` prefix just tries to run `psutil` as a
Windows command and fails immediately - it is not a partial install of the rest of the list, it did nothing at
all.

**Fix applied**: `conda activate home_credit_env` first, then re-run the upgrade there. Confirmed working - Gate 4
then real-ran clean end to end (all 10 integrity checks PASSED).

**Standing lesson reinforced**: when handing the user a fix for an environment-level (not code-level) error,
(1) verify the fix against real, current package-release information via web search rather than recalling stale
version-compatibility knowledge, since these facts change with every release, and (2) always confirm WHICH conda
environment the traceback's own file paths point to before telling the user where to run the install - a fix
applied in the wrong environment looks identical to "nothing happened" until the notebook is re-run and fails the
same way again.

## Lesson #18 - BP1 Gate 5 build: verifying a per-instance-SHAP code path the fixture's champion can't exercise (2026-09-22)

**Context**: Gate 5 needed per-instance (row-level) SHAP explanations for reason codes, not Gate 4's
class-averaged global top-10. This required new normalization logic to pick out each sampled row's SHAP values
for its OWN predicted class, from whatever shape shap.TreeExplainer / shap.LinearExplainer return (list of
per-class arrays, or a 3D array whose class axis could be last or middle depending on explainer/version) -
logic never exercised in Gate 4, which only ever averaged across classes.

**Standalone check run before delivery** (the fixture's champion is always logistic_regression, so it only ever
exercises the LinearExplainer branch - same limitation noted in Lesson #16): fit a RandomForestClassifier on
synthetic multiclass text data, ran shap.TreeExplainer on it, and confirmed this environment's shap 0.51.0
returns a (n_samples, n_features, n_classes) 3D array for a tree ensemble - the `arr.shape[-1] == N_CLASSES`
branch. Verified the per-row indexing (`arr[np.arange(n), :, predicted_class_per_row]`) picks out the correct
shape and that every reported reason code passed the nonzero-TF-IDF-weight grounding check (0 grounding
failures) - i.e. the code path is correct, not just shaped correctly.

**Reinforces**: whenever new indexing/branching logic is added for a code path the synthetic fixture's fixed
champion type cannot reach, write a standalone, minimal reproduction of that exact path before delivery rather
than trusting that "it looks like Gate 4's already-verified pattern." A subtly different array layout (SHAP's
class axis position varies by explainer type and library version) is exactly the kind of thing that looks
right until it silently mis-attributes reason codes to the wrong class.

## Lesson #19 — BP1 Gate 6: polars deprecation hardening in an already-verified module (2026-09-22)

**What happened:** While writing Gate 6's pytest suite (`tests/shared/test_taxonomy_mapper.py`) against
`src/taxonomy/taxonomy_mapper.py`, real `DeprecationWarning`s surfaced under polars 1.44.2 — not a crash, not a
test failure, just warnings. Two APIs used in the already-delivered, already real-run-confirmed module were
deprecated after it was written: `pl.read_csv(..., dtypes={...})` / `pl.scan_csv(..., dtypes={...})` (the
`dtypes` kwarg was renamed `schema_overrides` in polars 0.20.31) and `.replace(mapping, default=...)` (superseded
by `.replace_strict(mapping, default=...)` in polars 1.0.0 — `.replace()` still works but is deprecated when a
`default` is supplied). Gate 2 had already real-run successfully with the pre-fix code, so nothing was broken
in production — this was a forward-looking hardening finding, not a bug report.

**Why this needed a decision, not a silent fix:** the project's standing sensitivity to unauthorized changes to
already-verified, already real-run-confirmed code (explicit user instruction earlier this session) meant this
could not be patched without asking first, even though the fix was mechanical. Reported to the user with both
options (fix now vs. track as an open item); user chose fix now.

**Fix applied (5 call sites in `src/taxonomy/taxonomy_mapper.py`, lines 122, 145, 148, 161, 171):**
`dtypes=` → `schema_overrides=` (3 sites: `cfpb_bucket_expr`'s unused none, `load_banking77_with_bucket`'s two
`pl.read_csv` calls, `load_cfpb_with_bucket`'s `pl.scan_csv`), `.replace(mapping, default=X)` →
`.replace_strict(mapping, default=X)` (2 sites: `cfpb_bucket_expr`, `load_banking77_with_bucket`'s bucket_expr).

**Verification before touching the real file:** patched an exact copy in Claude's cloud sandbox first, then ran
the full 52-test Gate 6 pytest suite with `-W error::DeprecationWarning` (fails any test that still emits a
polars DeprecationWarning) — 46 passed / 6 skipped (the 6 skips are `test_gate_artifacts.py`'s real-artifact
checks, which correctly skip with no project root present in the sandbox), zero warnings. Confirmed
`requirements.txt` pins `polars>=1.9`, well above the `1.0.0` minimum `replace_strict` requires, so no version
compatibility risk on the user's real environment. Only then were the same 5 edits applied verbatim to the real
device file via exact string replacement (never retyped by hand), and the resulting line numbers were confirmed
unchanged (122/145/148/161/171) — no other code moved.

**Still required for real-run confirmation:** the user needs to re-run Gate 2's notebook (the only gate that
calls `load_cfpb_with_bucket` / `load_banking77_with_bucket` / `cfpb_bucket_expr` against real data) once, for
real, to confirm the patched module still produces the same real numbers Gate 2 already recorded (93.4% CFPB
out-of-scope, CFPB Gold 1,048,575 rows, BANKING77 Gold 13,083 rows) — sandbox/synthetic-fixture verification
alone is never a substitute for the real run, per the project's two-checkpoint standard.

**Lesson #19 update — REAL-RUN CONFIRMED (2026-09-22):** user re-ran Gate 2's notebook for real against the
patched `taxonomy_mapper.py`. Result: 93.4% CFPB out-of-scope (matches the ~93.45% documented figure), CFPB Gold
1,048,575 rows, BANKING77 Gold 13,083 rows, all 7 Gate 2 integrity checks PASSED — identical to Gate 2's
original real-run numbers before the patch. The `dtypes=`→`schema_overrides=` and `.replace()`→`.replace_strict()`
rename is confirmed behavior-preserving on real data, not just in the sandbox fixture. Closed.

## Lesson #20 — BP1: shared config file wiped by re-running an earlier gate (2026-09-22)

**What happened:** Gate 1's notebook (`bp1_customer_intent_classification_g1_business_understanding.ipynb`)
wrote `configs/bp1_customer_intent_classification.yaml` with a blind full-file overwrite (`open(path, "w")` +
a hardcoded template string) every time it ran, rather than the targeted patch pattern Gates 2-5 use. When the
user re-ran Gate 1 today (while verifying the Lesson #19 polars fix), that overwrite silently destroyed the
`gate3_model_benchmark`, `gate4_statistical_validation`, and `gate5_decision_layer` blocks Gates 3/4/5 had
already appended to that same file earlier in the day. Confirmed by direct inspection, not guessed: the real
file's mtime (04:34:48 UTC) matched `policy.json`'s (Gate 1's other output) and postdated Gate 5's summary JSON
(03:44:31 UTC) - Gate 1 had been re-run after Gates 3/4/5 completed. Nothing was actually lost: Gates 3/4/5's
own artifact files (`gate3_cv_benchmark_results.csv`, `gate4_statistical_validation.json`,
`gate5_decision_layer_summary.json`, `model_inventory_entry.json`) are separate files Gate 1 never touches, and
all their real numbers were still intact.

**Deeper cause found while investigating:** Gates 3, 4, and 5's own block-write logic was ALSO order-fragile
among themselves - each did `config_text.split(own_marker)[0]`, which discards everything from its own marker
to the end of the file. That's safe only when gates are always re-run in strict ascending order; re-running an
EARLIER gate (e.g. Gate 3) after a LATER one (Gate 4 or 5) had already appended its block would silently wipe
the later gate's block too, even without Gate 1's specific bug.

**Fix:** added `src/utils/bp1_config_sync.py` - two functions, `write_front_matter()` (Gate 1's own section)
and `write_gate_block()` (one named, marker-delimited block per gate), both order-independent: each locates
only the section it owns by its own marker and leaves every other section - front matter or any other gate's
block - untouched, regardless of what already exists or in what order. Verified with a synthetic test
reproducing both the real incident (Gate 1 re-run after Gates 3/4/5) and the deeper scenario (Gate 3 re-run
after Gates 4/5) - both preserve everything correctly; final output re-parses as valid YAML with every field
intact. Patched Gates 1, 3, 4, and 5's notebooks to use these functions instead of their own inline logic -
verified via `json.load` (valid notebook structure) and `ast.parse` (valid Python) on each of the 4 patched
notebooks; `nbformat`/`pyflakes` were not installed in the available check environment, so this audit relied on
`ast.parse` + manual review of the diff instead for this one fix.

**Repair of the currently-wiped state:** not needed - the user chose to re-run Gates 1 through 5 from the
beginning rather than have the missing blocks reconstructed from the existing artifact files. Since a single
forward pass (1->2->3->4->5, never re-run out of order) never triggered the bug even before this fix, that
re-run reproduces a fully correct config file on its own; this fix's benefit is protecting every re-run after
today, including inside the Gate 6 notebook still to be built.

## Lesson #21 — BP2 Gate 3: real Windows crash during first real run, uncapped CV concurrency across all candidates (2026-09-22)

**What happened:** The user's first real run of `bp2_customer_friction_classification_g3_model_benchmark.ipynb`
ended in a real, reported Windows crash: Event Viewer showed a Kernel-Power Event 41 (Critical, unclean
shutdown), immediately followed by boot-time fallout typical of an abrupt/hard reset (VBS/DRTM check failure,
BitLocker volume-master-key retrieval failure, crash dump init failure, driver reload warnings on
AMD platform sensor / mic / webcam array). The user confirmed directly this occurred while running this exact
notebook. A real, previously-recorded timing check (file mtimes: no `gate3_cv_benchmark_results.csv` existed
yet, consistent with the crash landing mid-run rather than after completion) supported this timing but did not
by itself prove a cause — Kernel-Power Event 41 is a generic "unclean shutdown" signal that a freeze, a driver
crash, a thermal shutoff, and a real power loss all produce identically.

**Root cause identified via code review (not from a crash dump — none has been reviewed):** the CV benchmark
loop (Section 9) runs all 6 candidate models under `joblib.parallel_backend("threading", n_jobs=cv_n_jobs)` +
`cross_validate(..., n_jobs=cv_n_jobs)`. Before this notebook was first run, only `hist_gradient_boosting` had
a reduced `cv_n_jobs` (2); every other candidate ran at the full `N_JOBS` (=16, a SYNTHETIC hardware-benchmark
recommendation from `hardware_benchmark_summary.json`, never derived from this specific workload). Two distinct
risk mechanisms were present, neither previously fully mitigated:
1. **Peak memory** — `hist_gradient_boosting` requires a densified float32 copy of the feature matrix
   (~2.4GB, code-review estimate, never profiled for real) *before* any fold-level split; under threading-backend
   concurrency this could have up to `n_splits`(=5) fold-level copies resident at once, since
   `assert_within_ram_ceiling()` only checked headroom *before* the CV loop started, never continuously during it.
2. **Sustained CPU / thermal load** — independent of any single candidate's memory footprint: this notebook's
   real dataset (816,717 trainable rows, from BP2 Gate 2's real run) is ~63x larger than any prior real workload
   in this project (BP1 Gate 3 benchmarked ~13,083 BANKING77 rows), so total wall-clock time at high concurrent
   CPU utilization across all 6 candidates is far longer than anything previously run for real here — a risk
   category this project had no prior precedent for, and one the user explicitly named separately from RAM/CPU
   peaks ("thermal freeze").

**Fix (comprehensive, covering every candidate and both risk categories — supersedes an earlier, narrower fix
that capped only `hist_gradient_boosting`):**
- Explicit per-candidate CV concurrency caps for all 6 models: `hist_gradient_boosting` tightened to `n_jobs=1`
  (from the previously applied `n_jobs=2`, given the confirmed real crash); `random_forest` and `catboost`
  newly capped to `n_jobs=2` each (real per-fold CPU/memory cost: 100 trees x max_depth=20, and per-fold target
  statistics over the 2,970-distinct-value `Company` column, respectively); `logistic_regression`, `xgboost`,
  `lightgbm` capped to `min(4, N_JOBS)` rather than left uncapped (`cv_settings['n_splits']==5` makes anything
  above 5 pointless regardless).
- A pre-candidate (not just post-candidate) adaptive memory check: live RAM headroom is read via
  `memory_headroom_gb()` immediately before each candidate's CV starts; below a 4GB threshold, that candidate
  is forced to `n_jobs=1` regardless of its planned cap.
- A 20-second precautionary pause between candidates, addressing sustained-CPU/thermal load as its own category
  — `psutil` exposes no portable CPU temperature reading on Windows, so this is a documented precaution, not a
  measured thermal response.
- Every CV result row now records `cv_n_jobs_used` and `ram_headroom_gb_before_candidate`, so the real run's
  own console output and `gate3_cv_benchmark_results.csv` are self-documenting evidence of what concurrency and
  headroom applied per candidate.
- Model hyperparameters (`n_estimators`, `max_depth`, `iterations`, etc.) were deliberately left untouched —
  this fix is concurrency/pacing/monitoring only and does not compromise the real benchmark's fidelity.

**Verification before touching the real file:** the patch was applied via a Python script performing exact
string replacements guarded by `assert content.count(old) == 1` per edit (never hand-retyped from memory),
against the real current file content read directly. Verified via `ast.parse` (valid Python) and `python3 -m
pyflakes` (0 issues) on the patched code cell, both standalone and after being embedded back into the rebuilt
`.ipynb`'s JSON structure. The pre-hardening notebook (the exact version that was running at the time of the
real crash) was preserved as
`notebooks/bp2_customer_friction_classification/bp2_customer_friction_classification_g3_model_benchmark.PRE_HARDENING_BACKUP.ipynb`
before being overwritten, rather than discarded.

**Still required for real-run confirmation:** the user needs to re-run this hardened notebook for real. No
crash dump has been reviewed (`Get-WinEvent -FilterHashtable @{LogName='System'; Id=1001} -MaxEvents 3 |
Format-List Message` would give a definitive stop-code-level answer if the user wants one), so this fix remains
a plausible, not a proven, explanation for the specific crash — applied regardless because the underlying
uncapped-concurrency and no-thermal-pacing conditions are real risks independent of confirmation. If the
hardened notebook completes a real run cleanly, that will be recorded here as a Lesson #21 update, matching
Lesson #19's precedent for how this file tracks real-run confirmation after a fix.

**Lesson #21 update — REAL-RUN CONFIRMED, no crash (2026-09-22):** the user ran the hardened notebook for real. It completed the full 6-candidate benchmark with no crash and all 10 integrity checks PASSED - the comprehensive concurrency/thermal hardening held under the exact workload that previously crashed the laptop. Real result: champion = xgboost, held-out test f1_macro = 0.4559 (class imbalance ratio 152.0:1). 1 candidate failed: catboost (exception type/message not captured - user explicitly declined to investigate it, choosing to proceed to Gate 4 instead; champion selection is unaffected since it only considers candidates with status=="OK", by the same design BP1 Gate 3 already used for its own candidate failures). Held-out confusion matrix shows the large majority of errors concentrated between the two largest adjacent classes (31,669 MEDIUM_FRICTION->MEDIUM_HIGH_FRICTION, 5,547 the reverse), with the minority classes (LOW_FRICTION, HIGH_FRICTION) comparatively well-separated - a real, plausible pattern given the taxonomy's precedence rule, not asserted as a code defect without the per-class precision/recall detail. Still not confirmed as proof the fix addressed the specific reported crash mechanism (no crash dump was ever reviewed), but the absence of a crash across a full real run of the exact workload that crashed before is itself real, positive evidence. Closed as REAL-RUN CONFIRMED.

## Lesson #22 — BP2 Gate 3: CatBoost's own real Windows crash-hardening run left one candidate failing (`RuntimeError: Cannot clone object CatBoostClassifier(...)`), now root-caused and fixed (2026-09-22)

**What happened:** BP2 Gate 3's real, crash-hardened run (Lesson #21) completed cleanly but recorded one open,
not-yet-investigated candidate failure: `catboost` — `RuntimeError: Cannot clone object CatBoostClassifier(...),
as the constructor either does not set or modifies parameter cat_features`. At the time, the user explicitly
declined to investigate and chose to proceed to Gate 4, since champion selection (xgboost) was unaffected. It
remained a recorded open item until this fix.

**Root cause (sandbox-reproduced, not guessed):** using the exact real `CATBOOST_KWARGS` construction from
`src/features/bp2_friction_features.py`'s `make_candidates()`, Claude reproduced the identical error in its own
cloud sandbox, then diagnosed it directly: `CatBoostClassifier.get_params()['cat_features']` returns a
newly-built list object on every single call — verified directly, two `get_params()` calls on the same
untouched, never-mutated model instance return list objects that are equal in value but not the same object
(`is` returns `False`). This project's installed scikit-learn (1.8.0) added a strict post-clone identity check
inside `clone()` (`sklearn/base.py`): it requires `new_object_params[name] is params_set[name]` for every
constructor parameter — identity, not `==`. `cross_validate()` calls `clone()` once per CV fold internally, so
any `CatBoostClassifier` built with a `cat_features` constructor argument fails this check on every real run
under this environment's installed scikit-learn version. This is a genuine upstream CatBoost/scikit-learn
incompatibility, not a defect in this project's own code — and notably, this project's *earlier* fix (passing
`cat_features` as a constructor argument at all) was itself already a deliberate workaround for a *different*
real failure: routing `cat_features` through `cross_validate`'s fit-params mechanism fails separately, because
CatBoost does not support scikit-learn's metadata-routing framework. Both of scikit-learn's normal integration
paths are broken for CatBoost in this environment, for two unrelated reasons — which is why this sat as an
unexplained "just fails" open item until it was actually root-caused.

**Fix:** CatBoost now gets its own manual per-fold CV loop (`_manual_cv_for_catboost`, new Section 8c) instead
of going through `cross_validate()` at all — it constructs a brand-new `CatBoostClassifier` by hand for every
fold rather than relying on `clone()`, sidestepping the broken machinery entirely. It uses the identical
`StratifiedKFold` splits (same `skf` instance, same `random_state`) every other candidate uses, so results stay
directly comparable across all 6 candidates. `CATBOOST_KWARGS` was extracted once so both the manual CV loop and
the existing champion-refit path (Section 11, a plain `.fit()`/`.predict()` call that was never affected by this
bug, since it never calls `clone()`) construct CatBoost identically — one source of truth, no drift risk
(HYPER). Every other candidate's code path is untouched.

**Verification before touching the real file:** the manual-CV replacement logic was first verified mechanically
in Claude's own sandbox against a small hand-built frame (never presented as a real result) to confirm it
executes without hitting `clone()` and returns correctly-shaped scores. The patch itself was then applied to the
real notebook via a Python script performing exact string replacements guarded by
`assert content.count(old) == 1` per edit (5/5 anchors matched exactly once — never hand-retyped from memory),
against the real current file content read directly from the device. Verified via `json.load` (valid notebook),
`ast.parse` + `compile()` (valid, compilable Python) on the patched cell, and a `diff` against the pre-patch
version confirming the change was exactly the 5 intended edits and nothing else. The pre-fix notebook was
preserved as
`notebooks/bp2_customer_friction_classification/bp2_customer_friction_classification_g3_model_benchmark.PRE_CATBOOST_FIX_BACKUP.ipynb`,
not discarded — same standing practice as Lesson #21's backup.

**Still required for real-run confirmation:** the user needs to re-run this notebook for real to get a genuine
6/6 candidate benchmark. **Important cascading consideration, flagged before the re-run, not after:** if
CatBoost's real macro-F1 beats the currently recorded champion (xgboost, CV mean 0.4584), CatBoost becomes the
new BP2 champion — and Gates 4, 5, 6 and the executive-rollup notebook all read the champion identity live from
this gate's own output, so they would all need to be re-run afterward too (not re-coded — their logic is already
champion-agnostic by design — just re-executed against the new champion). If xgboost remains champion, no
downstream re-run is needed; only this gate's own artifacts and config block refresh.

**Lesson #22 update — SUPERSEDED by a simpler decision, catboost removed entirely (2026-09-22):**
After the manual-CV-loop fix above was built, applied, and verified, the user weighed it against
the maintenance cost of carrying a special-cased workaround for one of six candidates and chose a
simpler path instead: **remove CatBoost from BP2's candidate set entirely** rather than keep
working around the clone() incompatibility. Applied via the same exact-anchor-replacement-with-
assertions methodology (all anchors matched exactly once), starting fresh from the pre-fix backup
so the diff stays clean: `bp2_customer_friction_classification_g3_model_benchmark.ipynb` now
benchmarks 5 candidates (logistic_regression, random_forest, hist_gradient_boosting, xgboost,
lightgbm) with no raw-categorical code path at all (`CATBOOST_FEATURE_COLS`,
`CATBOOST_CAT_FEATURE_INDICES`, `USES_RAW_CATEGORICAL`-driven branching all removed from the
notebook). `src/features/bp2_friction_features.py`'s `make_candidates()` (the Gate-6-extracted
HYPER module) was updated to match - catboost removed from its returned dict, the now-unused
`catboost_cat_feature_indices` parameter dropped, `USES_RAW_CATEGORICAL` emptied. Its raw-
categorical helper functions (`CATBOOST_FEATURE_COLS`, `reason_codes_for_row_raw_categorical`,
`reorder_predict_proba`) were deliberately KEPT as general-purpose, already-tested infrastructure
for any future BP/candidate needing a raw-categorical path, rather than deleted.

**Known, explicitly-stated tradeoff of this decision:** `Company` (2,970 distinct real values) is
exactly the kind of high-cardinality categorical feature CatBoost's native target-statistics
encoding is designed for - more so than the frequency-encoding the remaining 5 candidates use.
Removing CatBoost means BP2's benchmark no longer tests the one algorithm built for that specific
feature. This was surfaced to the user before the decision was made, not discovered after.

**Verification:** `tests/bp2_customer_friction_classification/test_bp2_friction_features.py` was
updated to match (6 candidate-count/catboost-specific test edits: `USES_RAW_CATEGORICAL` assertion,
`make_candidates()` call sites' now-dropped parameter, the 6-models test renamed to 5, and the
catboost-specific parameter test deleted outright since that candidate no longer exists). All 20
tests in this file were run for real in Claude's own cloud sandbox against the exact patched module
and test files staged from the device (legitimate pre-delivery verification per this project's
standing policy - never presented as a real-run confirmation, which remains the user's own real
`pytest tests/ -v` run) - **20 passed, 0 failed**. `pyflakes` on both patched files reported only
the same 2 pre-existing, unrelated cosmetic nits present before this change (confirmed by running
`pyflakes` on the pre-removal backups too) - zero new issues introduced. Backups preserved:
`bp2_customer_friction_classification_g3_model_benchmark.PRE_CATBOOST_FIX_BACKUP.ipynb` (the
Lesson #22 clone()-fix version, now superseded) and `...PRE_HARDENING_BACKUP.ipynb` (before that);
`src/features/bp2_friction_features.PRE_CATBOOST_REMOVAL_BACKUP.py` and
`tests/bp2_customer_friction_classification/test_bp2_friction_features.PRE_CATBOOST_REMOVAL_BACKUP.py`.

**Still required for real-run confirmation:** the user needs to re-run BP2 Gate 3 for real to get
the genuine 5-candidate benchmark, then Gates 4, 5, 6, and the executive rollup in sequence
afterward (champion-agnostic by design - no further code changes anticipated, only re-execution),
per the user's own stated plan to re-run all of BP2's gates.

## Lesson #23 — BP2 Gate 6 and the executive-rollup notebook: two real defects surfaced by re-running after CatBoost's removal, both fixed (2026-09-22)

**Context:** Following Lesson #22's final decision (CatBoost removed entirely from BP2), the user
re-ran BP2 Gate 6 and then the BP2 executive-rollup notebook for real on their own machine. Both
runs surfaced a real, previously-latent defect — neither caused by the CatBoost removal edits
themselves being wrong, but by other code in the project having silently assumed things that were
only ever true *because* CatBoost used to be a candidate that failed Gate 3.

**Defect 1 — Gate 6's real pytest run failed with exit code 2 ("1 error"), not a test failure.**
Real error, read directly from the user's own
`notebooks/bp2_customer_friction_classification/artifacts/gate6_pytest_output.log`:
`ModuleNotFoundError: No module named 'tests.bp2_customer_friction_classification.
test_bp2_friction_features.PRE_CATBOOST_REMOVAL_BACKUP'; '...test_bp2_friction_features' is not a
package`. Root cause: the Lesson #22 removal work preserved a backup copy of the edited test file,
`tests/bp2_customer_friction_classification/test_bp2_friction_features.PRE_CATBOOST_REMOVAL_BACKUP.py`,
in the same directory as the real test file — a naming convention that works fine for backups
outside `tests/` (e.g. the `src/features/` module backup, never scanned by pytest since
`pytest.ini` sets `testpaths = tests`), but this one still starts with `test_` and ends in `.py`,
so pytest's default collector tried to import it as a test module and failed on its invalid dotted
name, aborting collection of the entire 106-item suite before any real test ran. **Fix:** renamed
the file to end in `.py.bak` instead of `.py` (confirmed via `find tests -iname "*backup*"` that it
was the only file with this problem anywhere under `tests/`) — same content, same location, still
fully diffable, no longer matching pytest's `test_*.py` glob. No notebook or test code needed any
change; Gate 6's own assertion behavior (stopping on a non-clean pytest result rather than
continuing) was correct and is exactly what caught this.

**Defect 2 — the executive-rollup notebook's own Section 11 integrity check failed:**
`dashboard_html_represents_gate3_failed_candidate`. Real root cause, read directly from
`bp2_customer_friction_classification_executive_rollup_report.ipynb`'s own source: the check was
written as `_embedded_json["kpis"]["n_gate3_failed_candidates"] >= 1 and
len(_embedded_json["gate6_detail"]["gate3_failed_candidates_detail"]) >= 1` — a hardcoded
assumption that Gate 3 will always have at least one failed candidate, which was only ever true
because CatBoost used to fail there (Lesson #22). With CatBoost removed, Gate 3 now legitimately
has 0 failed candidates, so `>= 1` is false and the check fails even though every real output
(dashboard HTML, DOCX, XLSX, PPTX, manifest) was generated correctly. Before writing a fix, every
call site in `src/reporting/bp2_rollup_helpers.py` that consumes `gate3_failed_candidates_detail`
was checked (`grep -n "failed_candidate"`, all 8 matches read) — the DOCX narrative, the XLSX
sheet, and the dashboard's own narrative text all already iterate the list with a plain `for fd
in ...:` loop or an `... or "none"` fallback, so none of them needed any change; only this one
hardcoded assertion did. **Fix:** rewrote the check to `len(_embedded_json["gate6_detail"]
["gate3_failed_candidates_detail"]) == _embedded_json["kpis"]["n_gate3_failed_candidates"]` — a
real data-integrity check (the dashboard's represented count must exactly match the real KPI
count) instead of a hardcoded-existence check, correct whether that count is 0 or N. Verified in
Claude's own sandbox with 4 mock cases (0/0 pass, 1/1 pass, 1 KPI vs 0 represented correctly
fails — catches a dropped failure, 0 KPI vs 1 represented correctly fails — catches fabricated
content) before delivery — the check still catches real integrity problems in both directions, it
just no longer assumes a failure must exist. Diff-reviewed against a preserved backup
(`bp2_customer_friction_classification_executive_rollup_report.PRE_FAILED_CANDIDATE_CHECK_FIX_BACKUP.ipynb`)
to confirm this was the only change; notebook re-validated as valid JSON and the patched cell as
valid, compilable Python.

**Both defects were read from the user's own real run output (the pasted Gate 6 pytest traceback,
the pasted executive-rollup AssertionError) and root-caused by reading the actual real files on
the device — never guessed.** Neither required touching Gate 3, the champion identity, or any
already-real-run-confirmed BP2 Gate 1-5 artifact.

**Still required for real-run confirmation:** the user needs to re-run BP2 Gate 6 (pytest should
now collect cleanly, 106 items) and then the executive-rollup notebook (the failed-candidate check
should now pass with 0/0) for real, to get genuine confirmation both fixes work end to end.
