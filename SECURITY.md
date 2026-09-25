# Security

## Static analysis
`bandit` runs in CI on every push across `src/` and `tests/`. Current real result: **0 findings**
(two narrow, documented conventions are explicitly skipped: `B101` assert-statements in test files, and
`B404`/`B603` subprocess usage in the deployment-readiness verdict modules, which is its whole job —
each suppression is an inline `# nosec` on the exact flagged line, never a blanket ignore).

## Secrets
No API key, token, or credential is ever committed. The one real secret this project uses (a Google
Gemini API key for BP6) is read from an environment variable at runtime only. `.gitignore` excludes
`.env`, `*.pem`, and `*.key` project-wide.

## Dependencies
`requirements.txt` and `pyproject.toml` pin minimum versions for every real direct import found in `src/`
(derived by grepping actual imports, not copied wholesale from an unrelated template).

## Reporting a vulnerability
This is an independent portfolio project, not a maintained production service. If you find a real issue,
open a GitHub issue on this repository describing it — there is no dedicated security contact or bug
bounty program.
