# Power BI Executive Report

`Customer360_Navigator_Executive_Report.pbix` is the Priority 4 executive analytics
deliverable for the Customer360 Navigator Enterprise Suite — a 7-page Power BI
report built directly on top of the suite's real BP8 Gold layer (no synthetic or
illustrative data anywhere in the model).

## Contents

- **`pbix/Customer360_Navigator_Executive_Report.pbix`** — the report file. Open
  directly in Power BI Desktop.
- **`gold_tables/`** — the 11 real Gold parquet tables the report is built on,
  produced by BP8 Gate 2/Gate 3 from the same root Gate 4/Gate 5 artifacts the
  BP-level executive rollup dashboards use. Bundled here so the model can be
  refreshed or re-pointed without needing the full pipeline.
- **`build/`** — the build artifacts used to construct the report:
  - `POWERBI_BUILD_GUIDE.md` — page-by-page spec, including two honestly
    disclosed data gaps (no channel/"Submitted via" field, no literal
    multi-touchpoint journey-stage table in the Gold layer) and how each page
    was adapted around them rather than fabricating a substitute.
  - `queries.pq` — Power Query M for all 11 source tables plus one derived table.
  - `measures.dax` — the ~30-measure DAX library backing every card, chart, and
    KPI in the report.

## Pages

1. Executive Overview — KPI row, friction severity, decision outcomes, top
   root-cause driver, escalation volume trend (2014-2026).
2. Customer Friction — complaint trends, issue categories, complaints by product.
3. Customer Journey — review-priority-tier funnel (explicitly labeled as a real
   proxy for journey stage, not a literal touchpoint sequence).
4. Root Cause — Cramer's V driver Pareto, driver detail table, timely-response
   outcome trend.
5. Decision Engine — recommended-action distribution, priority score
   distribution, reason-code frequency.
6. Fairness — group selection rates, four-fifths-rule status, group metrics detail.
7. Product Opportunities — highest-priority product/issue clusters, recurring
   issue clusters treemap.

## Verification

Every KPI, chart proportion, and table value was independently cross-checked
against the raw Gold parquet files (recomputed directly, not read off the
report) before this push. All 7 pages matched ground truth exactly.
