// ============================================================================
// Customer360 Navigator — Power BI Power Query (M) source for all 11 real
// Gold tables. Priority 4 build, 2026-09-26.
//
// Grounded directly against the real files on disk at:
//   C:\Users\rnand\Documents\Customer360_Navigator_Enterprise_Suite\powerbi\gold_tables\
// (verified via a live device_bash pandas scan on 2026-09-26 — every column
// name, dtype, and distinct-value list below is real, not assumed.)
//
// HOW TO USE
// 1. Power BI Desktop -> Home -> Transform Data -> Manage Parameters -> New
//    Parameter. Name it exactly: GoldTablesFolder  (Type: Text)
//    Current Value:
//      C:\Users\rnand\Documents\Customer360_Navigator_Enterprise_Suite\powerbi\gold_tables\
//    (keep the trailing backslash)
// 2. For each query below: Home -> New Source -> Blank Query -> Advanced
//    Editor -> paste that query's M code in full -> Done -> rename the query
//    to the name given in its header comment.
// 3. Home -> Close & Apply once all 11 (or however many you want first) are
//    pasted in.
//
// Power BI Desktop's native Parquet.Document function (Power Query, 2023+
// builds) is used throughout — this is a real, shipped Power Query function,
// not a workaround. If your Power BI Desktop build predates it, run
// Help -> Check for Updates first.
// ============================================================================


// ----------------------------------------------------------------------------
// Query name: bp8_gold_friction_trends
// Real shape: 700 rows x 4 cols. Real months: 2014-04 .. 2026-09.
// Real friction_severity_class values (6): EXCLUDED_PENDING, EXCLUDED_UNKNOWN,
//   HIGH_FRICTION, LOW_FRICTION, MEDIUM_FRICTION, MEDIUM_HIGH_FRICTION
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_friction_trends.parquet")),
    #"Added MonthDate" = Table.AddColumn(Source, "MonthDate", each Date.FromText([complaint_month] & "-01"), type date),
    #"Changed Type" = Table.TransformColumnTypes(#"Added MonthDate", {{"n_complaints", Int64.Type}, {"Product", type text}, {"friction_severity_class", type text}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_escalation_trends
// Real shape: 521 rows x 4 cols.
// Real intervention_status values (5): EXCLUDED_EXCLUDED_PENDING,
//   EXCLUDED_EXCLUDED_UNKNOWN_NULL_RESPONSE,
//   EXCLUDED_EXCLUDED_UNTIMELY_RESPONSE_OVERLAPS_BP2, INTERVENTION_REQUIRED,
//   NO_INTERVENTION_REQUIRED
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_escalation_trends.parquet")),
    #"Added MonthDate" = Table.AddColumn(Source, "MonthDate", each Date.FromText([complaint_month] & "-01"), type date),
    #"Changed Type" = Table.TransformColumnTypes(#"Added MonthDate", {{"n_complaints", Int64.Type}, {"Product", type text}, {"intervention_status", type text}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_root_cause_outcome_trends
// Real shape: 660 rows x 5 cols.
// Real outcome_1_status values: same 5 as escalation_trends[intervention_status].
// Real outcome_2_status values (2): TIMELY_RESPONSE_FAILURE, TIMELY_RESPONSE_OK
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_root_cause_outcome_trends.parquet")),
    #"Added MonthDate" = Table.AddColumn(Source, "MonthDate", each Date.FromText([complaint_month] & "-01"), type date),
    #"Changed Type" = Table.TransformColumnTypes(#"Added MonthDate", {{"n_complaints", Int64.Type}, {"Product", type text}, {"outcome_1_status", type text}, {"outcome_2_status", type text}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_customer_intent_taxonomy_trends
// Real shape: 262 rows x 4 cols.
// Real common_taxonomy_bucket values (4): ATM_CASH_WITHDRAWAL,
//   CARD_ISSUANCE_AND_LIFECYCLE, OUT_OF_SCOPE_NO_BANKING77_OVERLAP, TRANSFERS
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_customer_intent_taxonomy_trends.parquet")),
    #"Added MonthDate" = Table.AddColumn(Source, "MonthDate", each Date.FromText([complaint_month] & "-01"), type date),
    #"Changed Type" = Table.TransformColumnTypes(#"Added MonthDate", {{"n_complaints", Int64.Type}, {"Product", type text}, {"common_taxonomy_bucket", type text}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_customer_intent_banking77_categories
// Real shape: 154 rows x 4 cols (77 BANKING77 categories x 2 splits).
// No month column — this is a train/test category catalog, not a trend.
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_customer_intent_banking77_categories.parquet")),
    #"Changed Type" = Table.TransformColumnTypes(Source, {{"category", type text}, {"common_taxonomy_bucket", type text}, {"split", type text}, {"n_examples", Int64.Type}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_product_opportunity_flags
// Real shape: 37,160 rows x 14 cols — the largest Gold table, row-level per
// (Company, Product, Sub-product, Issue, Sub-issue) combination.
// Real review_priority_tier values (4): HIGH, LOW, MEDIUM, NONE
// Real reason_codes values (6, pipe-delimited, can be blank ""):
//   "", ELEVATED_LAG, RECURRING, RECURRING|ELEVATED_LAG,
//   RECURRING|ELEVATED_LAG|HIGH_VOLUME, RECURRING|HIGH_VOLUME
// Real flag counts (of 37,160): recurring_flag=True 15,551 |
//   elevated_lag_flag=True 9,083 | high_volume_flag=True 4,091
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_product_opportunity_flags.parquet")),
    #"Parsed Dates" = Table.TransformColumns(Source, {
        {"first_complaint_date", each Date.FromText(Text.Start(_, 10)), type date},
        {"last_complaint_date", each Date.FromText(Text.Start(_, 10)), type date}
    }),
    #"Changed Type" = Table.TransformColumnTypes(#"Parsed Dates", {
        {"Company", type text}, {"Product", type text}, {"Sub-product", type text},
        {"Issue", type text}, {"Sub-issue", type text},
        {"n_complaints_total", Int64.Type}, {"review_priority_score", Int64.Type},
        {"review_priority_tier", type text}, {"reason_codes", type text},
        {"recurring_flag", type logical}, {"elevated_lag_flag", type logical},
        {"high_volume_flag", type logical}
    })
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_product_opportunity_reason_codes_exploded
// DERIVED query (not a 1:1 file load) — splits the pipe-delimited
// reason_codes column of bp8_gold_product_opportunity_flags into one row per
// individual code, for a real per-code frequency chart on Page 5/7. Blank
// reason_codes rows (cases with no flag) are dropped here on purpose — this
// table exists only to count how often each individual code fires.
// Build bp8_gold_product_opportunity_flags FIRST, then add this query.
// ----------------------------------------------------------------------------
let
    Source = bp8_gold_product_opportunity_flags,
    #"Filtered Non-blank" = Table.SelectRows(Source, each [reason_codes] <> null and [reason_codes] <> ""),
    #"Split Column by Delimiter" = Table.ExpandListColumn(
        Table.TransformColumns(#"Filtered Non-blank", {{"reason_codes", Splitter.SplitTextByDelimiter("|"), type list}}),
        "reason_codes"
    ),
    #"Renamed" = Table.RenameColumns(#"Split Column by Delimiter", {{"reason_codes", "reason_code"}}),
    #"Changed Type" = Table.TransformColumnTypes(#"Renamed", {{"reason_code", type text}})
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_root_cause_field_driver_ranking
// Real shape: 10 rows x 10 cols. This is the Pareto source for Page 4 — it
// is already rank-ordered by real Cramer's V per outcome_field.
// Real outcome_field sample: "outcome_1_intervention_required" (confirm the
// second outcome_field value in Model view — the earlier scan only printed
// the top row; do not assume a second label without checking the loaded
// data).
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_root_cause_field_driver_ranking.parquet")),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"outcome_field", type text}, {"rank", Int64.Type}, {"driver_field", type text},
        {"cramers_v", type number}, {"association_strength", type text},
        {"chi2_statistic", type number}, {"degrees_of_freedom", Int64.Type},
        {"p_value", type number}, {"n_rows_tested", Int64.Type}, {"n_distinct_levels", Int64.Type}
    })
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_decision_engine_action_breakdown
// Real shape: 3 rows x 5 cols. Real recommended_action values (3):
//   ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER (75.24% of population),
//   STANDARD_QUEUE (23.16%), PRIORITY_QUEUE_REVIEW (1.60%)
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_decision_engine_action_breakdown.parquet")),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"recommended_action", type text}, {"n_rows", Int64.Type},
        {"mean_priority_score", type number}, {"intervention_flag_rate", type number},
        {"pct_of_population", type number}
    })
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_decision_engine_tier_crosstab
// Real shape: 8 rows x 3 cols (5 tiers x up to 2 intervention_flag states).
// Real bp4_review_priority_tier values (5): HIGH, LOW, MEDIUM, NONE, UNSPECIFIED
// NOTE the column name here is bp4_review_priority_tier — NOT the same
// spelling as review_priority_tier in bp8_gold_product_opportunity_flags.
// Do not build a relationship between them without confirming the two
// column's value sets line up (product_opportunity_flags has no
// UNSPECIFIED level; this table does).
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_decision_engine_tier_crosstab.parquet")),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"bp4_review_priority_tier", type text}, {"intervention_flag", type logical}, {"n_rows", Int64.Type}
    })
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_decision_engine_disparate_impact
// Real shape: 4 rows x 4 cols. Real tags_group values (4): NO_TAG,
//   Older American, "Older American, Servicemember", Servicemember
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_decision_engine_disparate_impact.parquet")),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"tags_group", type text}, {"n_rows", Int64.Type},
        {"n_intervention_flagged", Int64.Type}, {"selection_rate", type number}
    })
in
    #"Changed Type"


// ----------------------------------------------------------------------------
// Query name: bp8_gold_decision_engine_summary
// Real shape: 1 row x 21 cols — BP7's Gate5 governance summary, verbatim.
// Real values as of the last regen (2026-09-25T06:13:24Z): live_row_count
// 1,048,575 | champion_rule_scheme correlation_aware_plus_lr_diagnostic |
// adverse_impact_ratio 0.908127 | flagged_four_fifths_rule False |
// lowest_selection_rate_group "Servicemember" | highest_selection_rate_group
// "Older American"
// ----------------------------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(GoldTablesFolder & "bp8_gold_decision_engine_summary.parquet")),
    #"Added GeneratedDate" = Table.AddColumn(Source, "GeneratedDate", each Date.FromText(Text.Start([generated_at_utc], 10)), type date),
    #"Changed Type" = Table.TransformColumnTypes(#"Added GeneratedDate", {
        {"bp_id", type text}, {"gate", Int64.Type}, {"live_row_count", Int64.Type},
        {"champion_rule_scheme", type text}, {"champion_weight_bp2", type number},
        {"champion_weight_bp3", type number}, {"champion_weight_bp4", type number},
        {"intervention_threshold", type number}, {"coverage_pct", type number},
        {"intervention_flag_rate", type number}, {"bp3_agreement_rate", type number},
        {"avg_reason_codes_per_row", type number}, {"mean_contribution_bp2", type number},
        {"mean_contribution_bp3", type number}, {"mean_contribution_bp4", type number},
        {"max_abs_reconstruction_error", type number}, {"adverse_impact_ratio", type number},
        {"flagged_four_fifths_rule", type logical}, {"lowest_selection_rate_group", type text},
        {"highest_selection_rate_group", type text}
    })
in
    #"Changed Type"
