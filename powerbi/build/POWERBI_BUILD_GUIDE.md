# Customer360 Navigator — Power BI Executive Report Build Guide
## Priority 4, 2026-09-26

This guide turns the 11 real Gold tables in `powerbi/gold_tables/` into the
7-page executive report you specified. It is grounded directly against the
real column names, row counts, and distinct values found on your machine on
2026-09-26 (see `queries.pq`'s header for how) — nothing below invents a
column or a category that isn't actually in the data.

**Companion files**: `queries.pq` (Power Query M for all 11 tables + 1
derived table) and `measures.dax` (the DAX measure library this guide
references by name). Load both first — this guide assumes they're already in
your model.

**Build order**: `queries.pq` → `measures.dax` → pages 1–7 below, in order,
since later pages reuse earlier measures.

---

## Known gaps — read this before Page 2 and Page 3

Your original 7-page spec asked for two things the current Gold layer does
not carry. Both are flagged honestly here rather than papered over with a
fabricated column:

- **Page 2 "channels"**: none of the 11 Gold tables carry a channel /
  "Submitted via" field. The real CFPB source data has one, but it was never
  aggregated into a Gold table by BP8. Page 2 below ships complaint trends,
  issue categories, and products — the three real ones — and Channels is
  left out with a note on the page rather than a fake bar chart.
- **Page 3 "journey stages"**: no BP8 Gold table represents a literal
  multi-touchpoint customer journey (first contact → escalation → resolution
  as a stage sequence). The real substitute is `bp8_gold_decision_engine_tier_crosstab`
  and `bp8_gold_product_opportunity_flags[review_priority_tier]` — both are
  real review-priority tiers (HIGH/MEDIUM/LOW/NONE/UNSPECIFIED), which is the
  closest honest proxy for "where a case sits in the review funnel." Page 3
  below is built and labeled around that proxy, not around an invented
  journey-stage taxonomy.

If a literal journey-stage sequence or a channel breakdown matters enough to
build for real, that's a small, real, additive BP8 Gate (a new
`bp8_gold_customer_journey_stages` / `..._channel_trends` table, same pattern
as Gate 3's decision-engine extension) — say so and I'll scope it before
touching Power BI again, rather than fabricating the visual now.

---

## Page 1 — Executive Overview

**Layout**: a KPI card row across the top, then 3 visuals below.

Card row (Card visual, one measure each):
- `[Total Scored Population]` — label "Population Scored (BP7 Gate 5)"
- `[Intervention Flag Rate]` — format as %, label "Intervention Rate"
- `[Escalation Rate]` — format as %, label "Escalation Rate"
- `[High Priority Review Cases]` — label "High-Priority Cases"
- `[Adverse Impact Ratio]` — format 0.000, label "Adverse Impact Ratio (4/5ths test)"

Row 2 — three visuals side by side:
- **Clustered column**: `bp8_gold_friction_trends[friction_severity_class]`
  on axis, `[Total Friction-Tracked Complaints]` on values — "Complaints by
  Friction Severity"
- **Donut/pie**: `bp8_gold_decision_engine_action_breakdown[recommended_action]`
  as legend, `pct_of_population` as values — "Decision Outcomes"
- **Card + subtitle**: `[Top Root Cause Driver]` — "Top Root Cause of
  Intervention" — pair with a small bar showing that driver's
  `cramers_v` from `bp8_gold_root_cause_field_driver_ranking`

Row 3 — one wide line chart:
- `bp8_gold_escalation_trends[MonthDate]` on axis, `n_complaints` split by
  `intervention_status`, area/line chart — "Escalation Volume Over Time
  (2014–2026)"

---

## Page 2 — Customer Friction

- **Line chart**: `bp8_gold_friction_trends[MonthDate]` on axis,
  `n_complaints` on values, `friction_severity_class` as legend — "Complaint
  Trends by Friction Severity"
- **Stacked bar**: `bp8_gold_customer_intent_taxonomy_trends[common_taxonomy_bucket]`
  on axis, `n_complaints` on values — "Issue Categories" (real values:
  ATM_CASH_WITHDRAWAL, CARD_ISSUANCE_AND_LIFECYCLE,
  OUT_OF_SCOPE_NO_BANKING77_OVERLAP, TRANSFERS)
- **Bar chart**: `bp8_gold_friction_trends[Product]` on axis,
  `[Total Friction-Tracked Complaints]` on values, top N filter (top 10) —
  "Complaints by Product"
- **Text box** (not a visual): "Channel breakdown is not in the current Gold
  layer — see Known Gaps in the build guide."

Add a slicer on `MonthDate` (both friction_trends and
customer_intent_taxonomy_trends) at the top of the page so the three visuals
filter together.

---

## Page 3 — Customer Journey *(built around the real tier proxy — see Known
Gaps above)*

- **Funnel visual**: `bp8_gold_decision_engine_tier_crosstab[bp4_review_priority_tier]`
  ordered HIGH → MEDIUM → LOW → NONE → UNSPECIFIED, values
  `[Total Tiered Population]` — "Cases by Review Priority Tier"
- **100% stacked bar**: same tier field on axis, `intervention_flag` as
  legend, `n_rows` as values — "Intervention Outcome by Tier"
- **Bar chart**: `bp8_gold_product_opportunity_flags[review_priority_tier]`
  on axis, `[Total Review Cases]` on values — "Review Cases by Tier
  (Product-Opportunity Layer)"
- **Card**: `[Tier Intervention Rate]` — "Overall Intervention Rate Across
  Tiers"
- Page header/subtitle text: "Tier = where BP4's review-priority scoring and
  BP7's decision engine place a case, used here as the closest real proxy
  for journey stage."

---

## Page 4 — Root Cause

- **Pareto** (combo chart — clustered column + line): filter
  `bp8_gold_root_cause_field_driver_ranking[outcome_field] = "outcome_1_intervention_required"`
  (verify this is the exact real value in Data view first), `driver_field`
  on axis sorted by `rank` ascending, `cramers_v` as columns,
  `[Cumulative Cramers V Pct]` as the line series on a secondary axis
  (0–100%) — "Root Cause Driver Pareto (Cramer's V)"
- **Table/matrix**: `driver_field`, `cramers_v`, `association_strength`,
  `p_value`, `n_distinct_levels` — "Driver Detail" (real real p-values are
  ~0.0 for the top drivers per the Gate5 run — format `p_value` with enough
  decimal places that it doesn't just show "0.00")
- **Line chart**: `bp8_gold_root_cause_outcome_trends[MonthDate]` on axis,
  `n_complaints` split by `outcome_2_status` — "Timely-Response Outcome
  Trend"
- **Card**: `[Timely Response Failure Rate]`

---

## Page 5 — Decision Engine

- **Bar or donut**: `bp8_gold_decision_engine_action_breakdown[recommended_action]`
  on axis, `n_rows` on values, data labels showing `pct_of_population` —
  "Recommended Action Distribution" (real split: 75.2% escalate-cluster,
  23.2% standard queue, 1.6% priority-queue review)
- **Gauge or card**: `[Weighted Avg Priority Score]`
- **Histogram-style bar**: `bp8_gold_product_opportunity_flags[review_priority_score]`
  binned (Power BI's built-in numeric binning on the axis field) — "Priority
  Score Distribution (Review Cases)"
- **Bar chart**: `bp8_gold_product_opportunity_reason_codes_exploded[reason_code]`
  on axis, `[Reason Code Occurrences]` on values — "Reason Code Frequency"
  (real codes: RECURRING, ELEVATED_LAG, HIGH_VOLUME, and their combinations —
  this chart needs the derived `reason_codes_exploded` query from
  `queries.pq`, not the raw pipe-delimited column)
- **Card**: `[Avg Reason Codes Per Case]`, `[BP3 Agreement Rate]`

---

## Page 6 — Fairness

- **Bar chart**: `bp8_gold_decision_engine_disparate_impact[tags_group]` on
  axis, `selection_rate` on values, reference line at the champion's overall
  intervention_flag_rate (from `bp8_gold_decision_engine_summary`) — "Group
  Selection Rates"
- **Card row**: `[Adverse Impact Ratio]`, `[Four-Fifths Rule Status]`,
  `[Lowest Selection Rate Group]`, `[Highest Selection Rate Group]`
- **Table**: full `bp8_gold_decision_engine_disparate_impact` (tags_group,
  n_rows, n_intervention_flagged, selection_rate) — "Group Metrics Detail"
- **Card**: `[Gold Layer As Of]`, labeled exactly "Gold Layer As Of" or
  similar — **do not label this "Live Monitoring Status."** It is the
  timestamp of the last Gate 5/BP8 Gold regeneration, not a live feed. Real
  live monitoring for BP7 is the separate Prometheus/Grafana stack (see
  `MONITORING.md`) — different system, not something a .pbix can embed.

---

## Page 7 — Product Opportunities

- **Table/matrix**: `Company`, `Product`, `Sub-product`, `Issue`,
  `Sub-issue`, `n_complaints_total`, `review_priority_tier`, `reason_codes` —
  sorted by `review_priority_score` descending, top 50 — "Highest-Priority
  Product Opportunities" (this is real row-level data across all 37,160
  cases — expect the table to be dense; consider a `review_priority_tier =
  "HIGH"` visual-level filter as the default view)
- **Card row**: `[Recurring Issue Cases]`, `[Elevated Lag Cases]`,
  `[High Volume Cases]`, each with its rate measure as a subtitle where one
  exists
- **Bar chart**: `Product` on axis, `[Total Complaint Volume (Flagged
  Cases)]` on values, top 10 — "Complaint Volume by Product (Flagged Cases
  Only)"
- **Treemap**: `Issue` then `Sub-issue` hierarchy, sized by
  `n_complaints_total`, filtered to `recurring_flag = TRUE` — "Recurring
  Issue Clusters"

---

## Cross-page notes

- **Relationships**: `friction_trends`, `escalation_trends`,
  `root_cause_outcome_trends`, and `customer_intent_taxonomy_trends` all
  share `Product` and `MonthDate` — you can relate them on `Product` (many-
  to-many, since none is a true dimension table) if you want a single
  cross-page Product slicer, but verify in Model view that the real
  `Product` value sets actually match before activating the relationship;
  I have not diffed the four tables' Product value lists against each other.
- **Color**: no brand palette was specified. Use Power BI's default theme
  or import one — this wasn't part of what you asked me to decide.
- **Everything above references a real column verified against the real
  parquet files.** Anything Power BI itself computes wrong (a mis-typed
  formula, a wrong axis) is something I can fix once you tell me what
  errored — I was not able to execute this inside a live Power BI session
  in this pass (see chat for why), so treat the DAX/M as reviewed-but-
  unexecuted, not verified end-to-end.
