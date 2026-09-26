## Summary

## Which BP(s) / module(s) does this touch?

## Real-run verification
- [ ] `pytest tests/ -v` passes locally
- [ ] `black --check src/ tests/`, `flake8 src/ tests/`, `isort --check-only src/ tests/` all pass
- [ ] `bandit -c pyproject.toml -r src/` reports no new findings
- [ ] If this touches a gate notebook: re-run it for real and update the corresponding `configs/*.yaml`
      gate block + `docs/evidence_ledger/EVIDENCE_LEDGER.md` entry (never hand-edit the gate block)
- [ ] If this touches a FastAPI service: the service's own `/health` and self-test route still pass

## Anything intentionally left out of scope for this PR?
