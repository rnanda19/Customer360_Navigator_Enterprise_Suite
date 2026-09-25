# Data Profile Report - Customer360 Navigator

Generated live by `notebooks/01_data_acquisition_profiling/01_data_acquisition_profiling.ipynb` on 2026-09-22T04:53:04.213423+00:00. Every figure below was computed during this run from the real files in `data/raw/` and `data/external/` - none estimated or carried over.

## CFPB Consumer Complaint Database export

- Row count (live): 1,048,575
- Column count: 15
- Duplicate `Complaint ID` groups: 0
- `Date received` range (as text, unparsed): 1/10/2026 .. 9/9/2026
- Taxonomy config drift check: [OK] Live CFPB row count (1,048,575) matches taxonomy_mapping.yaml's baked-in total - no drift.

### Null counts by column

| Column | Null count |
|---|---|
| Date received | 0 |
| Product | 0 |
| Sub-product | 21 |
| Issue | 0 |
| Sub-issue | 25,808 |
| Company public response | 570,861 |
| Company | 0 |
| State | 2,193 |
| ZIP code | 382 |
| Tags | 995,094 |
| Submitted via | 0 |
| Date sent to company | 0 |
| Company response to consumer | 2 |
| Timely response? | 0 |
| Complaint ID | 0 |

### Distinct value counts by column

| Column | Distinct count |
|---|---|
| Date received | 607 |
| Product | 15 |
| Sub-product | 61 |
| Issue | 96 |
| Sub-issue | 222 |
| Company public response | 12 |
| Company | 2,970 |
| State | 62 |
| ZIP code | 19,031 |
| Tags | 4 |
| Submitted via | 4 |
| Date sent to company | 623 |
| Company response to consumer | 6 |
| Timely response? | 2 |
| Complaint ID | 1,048,575 |

### Product distribution (live)

| Product | Row count | Fraction of total |
|---|---|---|
| Credit reporting, credit repair services, or other personal consumer reports | 477,097 | 45.50% |
| Credit reporting or other personal consumer reports | 430,204 | 41.03% |
| Debt collection | 44,493 | 4.24% |
| Checking or savings account | 27,952 | 2.67% |
| Credit card or prepaid card | 25,486 | 2.43% |
| Mortgage | 12,133 | 1.16% |
| Money transfer, virtual currency, or money service | 8,263 | 0.79% |
| Vehicle loan or lease | 7,215 | 0.69% |
| Credit card | 6,575 | 0.63% |
| Student loan | 3,948 | 0.38% |
| Payday loan, title loan, or personal loan | 3,308 | 0.32% |
| Payday loan, title loan, personal loan, or advance loan | 1,187 | 0.11% |
| Prepaid card | 434 | 0.04% |
| Debt or credit management | 259 | 0.02% |
| Credit reporting | 21 | 0.00% |

## BANKING77

- Row counts: train=10,003, test=3,080, total=13,083
- Categories found in data: 77 of 77 expected (missing: none; unexpected: none)
- Null counts: text=0, category=0
- Duplicate `text` rows: 0
- Text length (characters): min=13, max=433, mean=58.24, median=46.0
