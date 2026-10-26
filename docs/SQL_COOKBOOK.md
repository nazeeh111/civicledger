# SQL cookbook

Open `data/warehouse.duckdb` with DuckDB, or connect through Python. All examples operate on real data; values are signed unless a formula explicitly states otherwise. The complete source-to-metric transformations are in `sql/01_warehouse.sql`, dbt models and the export code.

## Reconcile commitments and preserve deobligations

```sql
SELECT fiscal_year, COUNT(*) AS actions,
       SUM(obligation) AS net_commitments,
       SUM(positive_obligation) AS gross_positive_commitments,
       SUM(CASE WHEN obligation < 0 THEN obligation ELSE 0 END) AS reversals
FROM fact_transactions
GROUP BY fiscal_year ORDER BY fiscal_year;
```

`net_commitments = gross_positive_commitments + reversals`. Compare with the official `spending_over_time` response using `spending_level: transactions` and the exact manifest filters, not lifetime award totals.

## Read a modification history with an explicit window

```sql
SELECT award_id, transaction_id, action_date, modification_number, obligation,
       cumulative_in_cohort_obligation, days_since_previous_observed_action,
       source_last_modified, source_url
FROM award_timeline
WHERE award_id = 'CONT_AWD_31310018C0001_3100_-NONE-_-NONE-'
ORDER BY action_date, source_last_modified, transaction_id;
```

The running sum uses an explicit `ROWS` frame. It is not lifetime award spending. A negative action is displayed, not removed.

## Keep dimensions and award facts at their proper grains

```sql
SELECT h.recipient_name, COUNT(*) AS observed_actions, SUM(f.obligation) AS net
FROM fact_transactions f
JOIN dim_recipient_history h USING (recipient_history_id)
GROUP BY h.recipient_name ORDER BY net DESC;
```

The history bundle is unique; joining by recipient UEI alone to a multiversion dimension would multiply actions. `mart_awards` aggregates actions before joining one latest award report. Never sum repeated `reported_potential_value` across modifications.

## Concentration with windows and conditional aggregation

```sql
WITH shares AS (
  SELECT *, concentration_weight /
            NULLIF(SUM(concentration_weight) OVER (PARTITION BY fiscal_year),0) AS share,
         ROW_NUMBER() OVER (PARTITION BY fiscal_year
                            ORDER BY concentration_weight DESC,recipient_id) AS rnk
  FROM recipient_year
)
SELECT fiscal_year, 10000*SUM(share*share) AS hhi,
       SUM(share) FILTER (WHERE rnk<=4) AS top4_share
FROM shares GROUP BY fiscal_year ORDER BY fiscal_year;
```

Weights are positive **recipient-year net balances**. Recipient totals stay signed in the warehouse. The reported-parent sensitivity is available separately in `parent_year` and `annual_concentration`.

## Compare peers and protect unknown offer denominators

```sql
SELECT fiscal_year,naics3,awards,recipients,
       single_offer_competed_transactions,
       known_offer_competed_transactions,single_offer_rate,
       missing_offers_transactions,hhi,competition_share
FROM peer_competition
WHERE adequate_peer_size AND known_offer_competed_transactions>=5
ORDER BY fiscal_year,single_offer_rate DESC;
```

This is action-record analysis. Use `analytics.peer_award_year` after `dbt build` for the companion award-year view, which avoids counting repeated modification reports as independent awards:

```sql
SELECT * FROM analytics.peer_award_year
WHERE adequate_peer_size AND known_offer_competed_award_years>=5
ORDER BY fiscal_year,single_offer_rate DESC;
```

## Supplier continuity and year-end patterns

```sql
SELECT fiscal_year,recipient_name,net_obligations,previous_observed_year_obligations,
       first_observed_year,last_observed_year
FROM recipient_entry_exit ORDER BY recipient_id,fiscal_year;

SELECT fiscal_year,calendar_month,transactions,net_obligations,positive_obligations
FROM monthly_patterns ORDER BY fiscal_year,calendar_month;
```

First and last observation do not establish federal-market entry or exit. September funding is descriptive; annual budgeting and option cycles offer benign explanations.

## Inspect source revision latency and model lineage

```sql
SELECT * FROM analytics.revision_lag ORDER BY fiscal_year;
SELECT * FROM analytics.recipient_cohorts
WHERE previous_observed_fy=fiscal_year-1 ORDER BY ABS(yoy_net_change) DESC;
```

`last_modified − action_date` describes the currently reported timestamp difference. It cannot recover an unobserved revision series.

## Profile the actual queries

```sql
EXPLAIN ANALYZE SELECT * FROM annual_concentration;
EXPLAIN ANALYZE SELECT * FROM peer_competition WHERE adequate_peer_size;
```

`data/processed/performance.json` records seven warm-cache runs with full result materialization; `profile_*.txt` retains actual plans. These tiny-cohort measurements justify no claims about million-row scale. The history join scans 4,683 facts and a keyed history dimension; concentration aggregates suppliers before windows; timeline queries sort within award; peer queries aggregate before joining rates. Materializing the repeatedly queried dbt award-year model removes repeated latest-record selection. This bounded cohort needs no speculative indexing or distributed infrastructure.
