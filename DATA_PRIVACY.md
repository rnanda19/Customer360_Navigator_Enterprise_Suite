# Data Privacy

## Source data
- **CFPB Consumer Complaint Database** — public, real, 1,048,575 rows in this project's extract. No
  government ID numbers, payment card numbers, or other directly identifying fields are present in the
  public dataset used here.
- **Banking77** (PolyAI) — public, real, 13,083 rows (10,003 train + 3,080 test). The sole real narrative
  free-text source in this suite; the CFPB extract used here carries no complaint-narrative column.

Neither dataset is redistributed in this repository — `data/raw/`, `data/processed/`, and `data/external/`
are all excluded via `.gitignore`. Only `.gitkeep` placeholders are committed.

## The one protected-class-adjacent field: `Tags`
CFPB's real `Tags` column (values like `Servicemember`, `Older American`) is **barred from every model's
feature set project-wide** — it is never trained on. It is used exactly once, as a read-only fairness-
monitoring passthrough: BP3 and BP7's disparate-impact audits group real predictions by this field to
check for adverse impact, never to condition a prediction on it.

## PII screening (BP6)
Before any narrative text reaches the GenAI resolution assistant, `src/genai/bp6_evidence_prep.py` runs a
real PII screen over the real Banking77 text. Real result on the last run: **0 PII instances flagged**.
The screened, de-identified text is what's ever sent to the Google Gemini API — never raw source text.

## Secrets
The one real external credential this project uses — a Google Gemini API key (BP6, Gate 5) — is read from
an environment variable only, never committed. `.gitignore` also excludes `.env`, `*.pem`, and `*.key`
project-wide. No other BP makes an external network call.
