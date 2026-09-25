# Raw Data Manifest — Customer360 Navigator

Generated from a live inspection and copy of the raw source files on 2026-09-21.
All figures below are measured directly from the files (line counts, byte sizes,
MD5 checksums) — none are estimated or assumed. Per the Master Plan's
zero-fabrication standard, this file is the source-lineage record for `data/raw/`
and `data/external/`.

## 1. File Inventory

| File | Location | Source | Bytes | Rows | MD5 |
|---|---|---|---|---|---|
| `cfpb_complaints.csv` | `data/raw/` | CFPB Consumer Complaint Database export | 322,577,548 | 1,048,575 data rows (1,048,576 incl. header; naive line count and real CSV parse agree here) | `04778658738ba2e1d98696eeacdf323e` |
| `banking77_train.csv` | `data/external/` | PolyAI BANKING77 (train split) | 839,073 | 10,003 data rows (CORRECTED 2026-09-21 - see Finding 6; a naive line count read 10,016 data rows / 10,017 incl. header) | `cec64185f4197906aabce0781ef9a19b` |
| `banking77_test.csv` | `data/external/` | PolyAI BANKING77 (test split) | 239,961 | 3,080 data rows (CORRECTED 2026-09-21 - see Finding 6; a naive line count read 3,084 data rows / 3,085 incl. header) | `8dcd9dc31b686c75ec1f24bf23c140cb` |
| `banking77_categories.json` | `data/external/` | PolyAI BANKING77 (label list) | 2,036 | 77 category strings | `8312ff01430af97fba5a113b7a490269` |

BANKING77 corrected total: **13,083 rows** (10,003 train + 3,080 test), real-parsed and confirmed by
`notebooks/01_data_acquisition_profiling/01_data_acquisition_profiling.ipynb`'s first real run on
2026-09-21 — not 13,100 as originally stated here. MD5 of `cfpb_complaints.csv` and each BANKING77
file matches byte-for-byte between the original source folder and the copy stored in this project —
only the row-count figures above were wrong, the files themselves are untouched. The CFPB file was
copied with a plain synchronous `cp` (took ~102 seconds on this hardware/mount); size and MD5 were
independently re-verified after the copy completed.

## 2. CFPB File — Schema (as delivered, 15 columns)

```
Date received, Product, Sub-product, Issue, Sub-issue, Company public response,
Company, State, ZIP code, Tags, Submitted via, Date sent to company,
Company response to consumer, Timely response?, Complaint ID
```

## 3. BANKING77 File — Schema

`banking77_train.csv` / `banking77_test.csv`: two columns, `text,category`.
`banking77_categories.json`: JSON array of the 77 intent label strings used in
`category`.

## 4. Findings That Require Attention Before BP Work Proceeds

These are real, measured observations — not assumptions — and each one interacts
directly with an ASSUMPTION flag already written into the Master Plan (Section 3
Data Strategy, Section 4 BP Methodology, Section 9 Regulatory & Compliance).

1. **Row count is exactly 1,048,576 — Excel's hard row cap (2^20).** This is not
   a coincidence worth ignoring: it strongly suggests this CFPB export was
   produced or last saved through Excel/a spreadsheet tool and was truncated at
   Excel's maximum row limit, not the full CFPB Consumer Complaint Database
   (whose public dataset has several million records spanning back to 2011).
   **Implication:** this file should be treated as a bounded extract, not the
   full population, until confirmed otherwise. Any BP that reports counts,
   trends over time, or population-level claims (BP4 journey analytics, BP5
   root-cause analytics, BP8 executive analytics) must state this file's actual
   date range and row count rather than implying full-population coverage.

2. **No narrative/complaint-text column is present.** The 15 columns above do
   not include a "Consumer complaint narrative" field. This confirms the Master
   Plan's Section 3/Section 4 ASSUMPTION flag: CFPB narrative text is NOT
   available in this extract. BP1 (Intent Classification) and BP6 (GenAI
   Resolution Assistant) as currently scoped for "CFPB text" must instead rely
   on BANKING77's `text` field for any text-model training/evaluation, or on
   the structured fields (Product/Sub-product/Issue/Sub-issue) as categorical
   inputs. This should be called out explicitly wherever BP1/BP6 notebooks are
   built — do not assume narrative text will appear later without re-verifying
   the source export.

3. **No demographic/protected-class column is present.** Consistent with how
   CFPB typically publishes this dataset (demographics are not part of the
   public complaint database), but directly relevant to Section 9's ECOA/Reg B
   fair-lending mapping: any fair-lending or disparate-impact analysis is
   **not supportable** on this field set. This should be stated as a hard
   limitation, not worked around with a proxy variable, per the zero-fabrication
   rule.

4. **Data is not a random sample — it appears date-ordered, most-recent first.**
   Spot-checking row 2 (`3/29/2024`) against the final rows (`9/6/2023`) shows
   the file is ordered with newer complaints near the top. Complaint IDs are
   not strictly monotonic with row order. Before using this file for any
   trend/time-series work (BP4, BP8), confirm the actual min/max date range and
   whether the ordering is a true global sort or an artifact of how the export
   was generated.

5. **Quoted-field commas will break naive comma-splitting.** At least one
   observed row contains a quoted company name with an internal comma
   (`"EQUIFAX, INC."`). Any loading code must use a real CSV/Parquet parser
   (Polars `read_csv` / DuckDB) rather than naive `split(",")` — this is a
   loading-correctness note, not a data-quality defect in the source file.

6. **BANKING77's original row counts (Section 1) were wrong — naive line counting over-counts
   quoted multi-line fields.** At least 13 rows in `banking77_train.csv` and 4 rows in
   `banking77_test.csv` contain a literal embedded newline inside the quoted `text` field, which a
   `wc -l`-style line count wrongly splits into multiple lines. A real CSV parser (Polars) correctly
   parses these as single rows, giving the corrected counts in Section 1 (13,083 total, not 13,100).
   Any future manual inspection of these files must use a real CSV parser, never a raw line count,
   to determine row counts — the same class of parsing-correctness issue as Finding 5, just for line
   counting instead of comma-splitting.

## 5. Storage Location

All four files live only under this project folder
(`C:\Users\rnand\Documents\Customer360_Navigator_Enterprise_Suite\data\raw\` and
`...\data\external\`), per the standing instruction to use no other location on
this machine. No copies were left in the Downloads source folder's mount other
than the originals the user provided, and no files were written to any other
path on this laptop.
