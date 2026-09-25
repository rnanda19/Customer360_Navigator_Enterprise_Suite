# Contributing

This is an independent portfolio project, built and run by one person (see the
[Execution boundary](README.md#execution-boundary-standing-rule-disclosed-on-purpose) section of the
README) — it isn't currently seeking external code contributions.

If you spot a real bug, a factual error, or a broken link, please open a GitHub issue describing it. Pull
requests are welcome for typo fixes and documentation clarity, but any change to notebook logic, model
code, or reported numbers has to go through this project's own standing rule: the change is proposed,
the owner runs it for real on their own machine, and the result is what gets merged — never a claimed
result that wasn't actually executed.

## Local setup
```bash
python -m pip install -e .
python -m pip install -r requirements.txt
pytest tests/ -v
```
See `README.md` → "Reproducing this locally" for the full notebook-execution workflow, and `Makefile` for
the shortcut targets (`make install`, `make test`, `make lint`).
