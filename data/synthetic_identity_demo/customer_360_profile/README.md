# Synthetic Golden Customer 360 Profile Demonstration

**Entirely fictional data, same disclosure standard as the parent
[`data/synthetic_identity_demo/`](../README.md) directory.** Identity Resolution proves this suite
can build a golden `customer_360_id`; this directory demonstrates what attaching real-shaped
content to that id would look like — profile, interactions, complaints, risk signals, products,
journey, and a recommended action — using `src/identity_resolution/customer_360_profile_demo.py`.

## What's here

- `synthetic_interactions.csv` — fictional interaction events (login, branch visit, call, chatbot
  session, etc.) per `customer_360_id`. Some customers deliberately have zero interactions — a real
  customer population isn't uniformly active, and giving everyone a full profile would itself be a
  small dishonesty.
- `synthetic_products.csv` — fictional product holdings (checking/savings account, credit card,
  auto loan) per `customer_360_id`.
- `synthetic_illustrative_complaint_examples.csv` — **fictional example records only.** Every row's
  `summary` field says so explicitly. These are hand-authored illustrative shapes, **never real
  CFPB rows** — they are never joined to, derived from, or counted in this suite's real BP1-8
  numbers anywhere. The real CFPB extract has no customer identifier to join against in the first
  place (see the parent directory's README and BP4's own architecture doc).
- `output/customer_360_profiles.json` — one nested profile per real golden `customer_360_id`,
  written by `python -m identity_resolution.customer_360_profile_demo` from the project root.

## What's computed for real vs. what's illustrative

- **Computed for real, from the synthetic data above:** `risk_signals` (interaction/product/
  complaint-example counts, days since last interaction) and `journey` (a real merge-and-sort of
  interaction and complaint-example records by timestamp) — both are real aggregation code, not
  hand-typed numbers.
- **Illustrative, disclosed as such:** `recommended_action_demo` reuses BP7's real, deployed
  4-value action vocabulary verbatim (copied from
  `src/features/bp7_decision_engine_features.py::_recommended_action_expr`, with a test that keeps
  the two in sync) but picks among them with a small, transparent demo rule — **not** BP7's real
  trained/rule-scored decision engine, which has never been run on this synthetic data and makes no
  claim of having been.

## Running it

```bash
python -m identity_resolution.customer_360_profile_demo
```

## What this does not claim

Not applied anywhere else in this repository. BP1-BP8's own pipelines, dashboards, and reports
never reference this directory. It does not claim BP7's actual decision engine ran on this data,
and it does not claim any of these interaction/product/complaint-example records are real.
