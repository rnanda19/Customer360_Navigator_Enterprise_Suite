# Synthetic Multi-Source Customer Identity Demonstration

**This directory is entirely fictional data and exists only to demonstrate what a real
identity-resolution / golden-record layer looks like.** It is disclosed here, repeatedly and
explicitly, because this project's own governing rule is zero fabrication over the real dataset —
and identity resolution over CFPB complaints is structurally impossible to do honestly, because
**the real CFPB extract this whole suite is built on has no customer identifier at all.** BP4's own
architecture doc states this plainly and is the reason BP4 performs event/issue-cluster journey
analytics instead of inventing a customer key that does not exist in the source data. That
disclosed limitation is a real, intentional scope boundary of this project — not a gap this demo
quietly papers over.

**Nothing in this directory is joined to, derived from, or ever mixed with any real CFPB row
anywhere in this project.** `customer_source_a.csv`, `customer_source_b.csv`, and
`customer_source_c.csv` are three small, hand-authored CSVs of invented people — invented names,
emails, phone numbers, and addresses. Any resemblance to a real person is coincidental. They model
three source systems a real financial institution might actually have (a core-banking system, a
CRM, and a web self-signup flow), each describing a handful of overlapping fictional customers
slightly differently, the way real source systems genuinely do (a maiden-name variant, an address
abbreviation, a typo'd digit in a phone number).

## What's here

- `customer_source_a.csv` / `_b.csv` / `_c.csv` — the three fictional source files (14 rows total).
- `output/identity_match_pairs.csv` — one row per source record, with its resolved
  `customer_360_id`, `match_score`, `match_method`, `survivorship_rule`, and `confidence` — written
  by running `python -m identity_resolution.run_demo` from the project root.
- `output/golden_customer_record.csv` — one row per resolved `customer_360_id`, with the
  survivorship-selected field values.

## The method (real code, not a mock)

`src/identity_resolution/entity_resolution.py` implements a genuine two-pass resolver:

1. **Deterministic matching** — records sharing an identical normalized email or an identical
   normalized (digits-only) phone number are merged via union-find.
2. **Probabilistic matching** — every remaining pair is scored on a disclosed, weighted blend of
   name/address/phone/email similarity (Python's stdlib `difflib.SequenceMatcher`, used here as a
   real but simplified stand-in for a production Jaro-Winkler/phonetic matcher — that substitution
   is stated plainly in the module's own docstring, not hidden). A pair merges only above a
   threshold calibrated against this fixture's own real computed scores.
3. **Golden record** — each resulting cluster gets one `customer_360_id`; the
   `most_recently_updated_source_record_wins` survivorship rule picks which source's field values
   are shown, while every contributing source row still appears in `identity_match_pairs.csv`.

On this real 14-row fixture, the resolver correctly: chains one fictional customer across all 3
sources via deterministic email+phone matching; correctly probabilistically matches two other
fictional customers each appearing under a slightly different name in 2 sources; and — the
important negative case — correctly **declines** to merge two different fictional people who share
a surname and a similar-shaped address, because their real computed similarity score falls below
the threshold. See `tests/identity_resolution/test_entity_resolution.py` for the exact numbers.

## Running it

```bash
python -m identity_resolution.run_demo
```

## What this does not claim

This is not applied anywhere else in this repository. BP1-BP8's own pipelines, dashboards, and
reports never reference this directory. It does not claim the real CFPB dataset has customer
identities to resolve — it demonstrates the *pattern* a real Customer 360 platform would use if the
underlying data supported it.
