"""
scripts/check_notebook_syntax.py — Customer360 Navigator

Reconstructs the notebook-syntax check this project has always relied on (referenced by
`Makefile`'s `notebook-check` target and `.github/workflows/ci.yml`'s `notebook-syntax-check` job)
but which was never actually committed to the repo — `scripts/check_notebook_syntax.py` did not
exist on disk, so both the Makefile target and CI's `python scripts/check_notebook_syntax.py ||
true` step were silently no-ops (the `|| true` swallowed the "file not found" error, so CI kept
reporting the job as passed without ever running a real check).

Rebuilt to match the exact real methodology already evidenced by this project's own historical
per-BP output logs (e.g. notebooks/bp1_customer_intent_classification/artifacts/
gate6_notebook_syntax_check_output.log): for every real .ipynb under notebooks/, three checks -
  1. nbformat.read() - the notebook's own JSON structure is valid.
  2. ast.parse() on every code cell (Jupyter magics/shell-escapes stripped first, since they are
     valid notebook syntax but not valid plain Python) - a real syntax error is a hard FAIL.
  3. pyflakes - reported per-notebook for visibility (unused imports, undefined names) but never
     flips a notebook to FAIL on its own, matching this project's own historical logs (pyflakes
     nits exist across a 66-notebook suite; none of the historical runs ever failed a notebook
     over them).
Prints [PASS <path>] / [FAIL <path>: <reason>] per notebook plus a final [RESULT] summary line,
in the same format the historical logs already show. Exits 1 if any notebook has a real nbformat
or ast failure (Makefile/CI can decide whether to treat that as blocking); pyflakes findings never
affect the exit code.
"""

from __future__ import annotations

import ast
import io
import re
import sys
from pathlib import Path

import nbformat
from pyflakes.api import check as pyflakes_check
from pyflakes.reporter import Reporter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"

# Matches a Jupyter/IPython magic or shell-escape line (%matplotlib inline, %%time, !pip install
# ...). These are valid notebook cell syntax but not valid plain Python, so ast.parse() must never
# see them - replaced with a same-length comment so line numbers in any real error stay accurate.
_MAGIC_LINE_RE = re.compile(r"^(\s*)(%{1,2}|!)")


def _strip_magics(source: str) -> str:
    lines = source.splitlines()
    out = []
    for line in lines:
        if _MAGIC_LINE_RE.match(line):
            out.append("# " + line)
        else:
            out.append(line)
    return "\n".join(out)


def _find_notebooks() -> list[Path]:
    return sorted(p for p in NOTEBOOKS_DIR.rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)


def _check_one(path: Path) -> tuple[bool, str]:
    """Returns (passed, message)."""
    try:
        nb = nbformat.read(path, as_version=4)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a real, concrete FAIL
        return False, f"nbformat read failed: {exc}"

    code_cells = [c for c in nb.cells if c.get("cell_type") == "code"]
    pyflakes_hits = 0
    for i, cell in enumerate(code_cells):
        source = _strip_magics(cell.get("source", ""))
        if not source.strip():
            continue
        try:
            ast.parse(source)
        except SyntaxError as exc:
            return False, f"ast.parse failed on code cell {i}: {exc}"

        buf = io.StringIO()
        reporter = Reporter(buf, buf)
        pyflakes_hits += pyflakes_check(source, f"{path.name}[cell {i}]", reporter)

    suffix = f" ({pyflakes_hits} pyflakes note(s))" if pyflakes_hits else ""
    return True, suffix


def main() -> int:
    notebooks = _find_notebooks()
    if not notebooks:
        print(f"[RESULT] No notebooks found under {NOTEBOOKS_DIR}.")
        return 1

    n_failed = 0
    for path in notebooks:
        rel = path.relative_to(PROJECT_ROOT)
        passed, message = _check_one(path)
        if passed:
            print(f"[PASS] {rel}{message}")
        else:
            n_failed += 1
            print(f"[FAIL] {rel}: {message}")

    print()
    if n_failed == 0:
        print(f"[RESULT] All {len(notebooks)} notebook(s) passed nbformat + ast + pyflakes checks.")
        return 0
    print(f"[RESULT] {n_failed} of {len(notebooks)} notebook(s) failed nbformat/ast checks.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
