-- Grain: one source transaction/revision in this retrieval snapshot, not one award.
CREATE OR REPLACE TABLE fact_transactions AS
SELECT contract_transaction_unique_key AS transaction_id,
 contract_award_unique_key AS award_id, award_id_piid AS piid,
 modification_number, transaction_number,
 CAST(action_date AS DATE) AS action_date,
 CAST(action_date_fiscal_year AS INTEGER) AS fiscal_year,
 CAST(federal_action_obligation AS DECIMAL(20,2)) AS obligation,
 CAST(total_dollars_obligated AS DECIMAL(20,2)) AS reported_total_obligated,
 CAST(current_total_value_of_award AS DECIMAL(20,2)) AS reported_current_value,
 CAST(potential_total_value_of_award AS DECIMAL(20,2)) AS reported_potential_value,
 recipient_uei AS recipient_id, recipient_duns, recipient_name,
 recipient_doing_business_as_name AS recipient_dba,
 recipient_parent_uei AS parent_id, recipient_parent_duns AS parent_duns,
 recipient_parent_name AS parent_name,
 recipient_city_name AS recipient_city, recipient_state_code AS recipient_state,
 recipient_country_code AS recipient_country,
 awarding_agency_code AS agency_id, awarding_agency_name AS agency_name,
 awarding_sub_agency_code AS subagency_id, awarding_sub_agency_name AS subagency_name,
 awarding_office_code AS office_id, awarding_office_name AS office_name,
 funding_agency_code AS funding_agency_id, funding_agency_name,
 naics_code AS naics, naics_description, product_or_service_code AS psc,
 product_or_service_code_description AS psc_description,
 extent_competed_code AS competition_code, extent_competed AS competition,
 try_cast(number_of_offers_received AS INTEGER) AS offers_received,
 solicitation_procedures_code, solicitation_procedures,
 type_of_set_aside_code AS set_aside_code, type_of_set_aside AS set_aside,
 award_type_code, award_type, type_of_contract_pricing_code AS pricing_code,
 type_of_contract_pricing AS pricing_type,
 transaction_description AS description,
 CAST(last_modified_date AS TIMESTAMPTZ) AS source_last_modified,
 CAST(initial_report_date AS TIMESTAMPTZ) AS source_initial_report,
 usaspending_permalink AS source_url,
 CAST(period_of_performance_start_date AS DATE) AS performance_start,
 CAST(period_of_performance_current_end_date AS DATE) AS performance_end,
 -- Identifies an OBSERVED attribute bundle. This is not a legal corporate-history assertion.
 md5(concat_ws('|',recipient_uei,recipient_name,recipient_parent_uei,
               recipient_city_name,recipient_state_code,recipient_country_code)) AS recipient_history_id,
 competition_code IN ('A','D','F') AS is_competed,
 competition_code IS NULL AS competition_missing,
 -- Positive action obligations are a gross flow, not award ceilings or lifetime award spending.
 greatest(CAST(federal_action_obligation AS DECIMAL(20,2)),0) AS positive_obligation
FROM raw_transactions;

CREATE OR REPLACE TABLE dim_recipient_history AS
SELECT recipient_history_id, recipient_id, recipient_name, parent_id, parent_name,
 recipient_city, recipient_state, recipient_country,
 min(action_date) AS first_observed, max(action_date) AS last_observed,
 count(*) AS observed_transactions
FROM fact_transactions GROUP BY ALL;

CREATE OR REPLACE TABLE dim_agency AS
SELECT agency_id, agency_name, subagency_id, subagency_name, office_id, office_name,
 count(*) AS observed_transactions
FROM fact_transactions GROUP BY ALL;

CREATE OR REPLACE TABLE dim_classification AS
SELECT naics, naics_description, psc, psc_description,
 count(*) AS observed_transactions
FROM fact_transactions GROUP BY ALL;

-- Award grain: aggregate incremental obligations once; choose latest in-cohort reported stock separately.
CREATE OR REPLACE TABLE mart_awards AS
WITH flows AS (
 SELECT award_id, min(action_date) AS first_action, max(action_date) AS last_action,
 sum(obligation) AS net_obligations, sum(positive_obligation) AS positive_obligations,
 sum(CASE WHEN obligation<0 THEN obligation ELSE 0 END) AS negative_obligations,
 count(*) AS transaction_count, count(*) FILTER(WHERE obligation<0) AS deobligation_count,
 count(*) FILTER(WHERE modification_number NOT IN ('0','00','000','0000')) AS nonzero_modification_records,
 count(DISTINCT recipient_id) AS observed_recipient_count
 FROM fact_transactions GROUP BY award_id
), latest AS (
 SELECT *,row_number() OVER(PARTITION BY award_id ORDER BY action_date DESC, source_last_modified DESC, transaction_id DESC) AS rn
 FROM fact_transactions
)
SELECT flows.*,latest.piid,latest.recipient_id,latest.recipient_name,latest.parent_id,latest.parent_name,
 latest.naics,latest.psc,latest.competition,latest.competition_code,latest.offers_received,
 latest.description,latest.source_url,latest.reported_total_obligated,
 latest.reported_current_value,latest.reported_potential_value, latest.source_last_modified
FROM flows JOIN latest USING(award_id) WHERE latest.rn=1;

-- Histories are limited to the selected fiscal-year window. Cumulative balances do not begin at award inception.
CREATE OR REPLACE VIEW award_timeline AS
SELECT *,
 sum(obligation) OVER(PARTITION BY award_id ORDER BY action_date,source_last_modified,transaction_id
 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_in_cohort_obligation,
 lag(obligation) OVER(PARTITION BY award_id ORDER BY action_date,source_last_modified,transaction_id) AS previous_action_obligation,
 date_diff('day',lag(action_date) OVER(PARTITION BY award_id ORDER BY action_date,source_last_modified,transaction_id),action_date) AS days_since_previous_observed_action
FROM fact_transactions;

CREATE OR REPLACE VIEW recipient_year AS
SELECT fiscal_year,recipient_id, arg_max(recipient_name,action_date) AS recipient_name,
 sum(obligation) AS net_obligations, sum(positive_obligation) AS positive_obligations,
 count(*) AS transactions,count(DISTINCT award_id) AS awards,
 greatest(sum(obligation),0) AS concentration_weight
FROM fact_transactions GROUP BY fiscal_year,recipient_id;

CREATE OR REPLACE VIEW parent_year AS
SELECT fiscal_year,coalesce(parent_id,recipient_id) AS parent_id,
 arg_max(coalesce(parent_name,recipient_name),action_date) AS parent_name,
 sum(obligation) AS net_obligations,greatest(sum(obligation),0) AS concentration_weight,
 count(DISTINCT recipient_id) AS legal_entities
FROM fact_transactions GROUP BY fiscal_year,coalesce(parent_id,recipient_id);

CREATE OR REPLACE VIEW annual_concentration AS
WITH shares AS (
 SELECT *,concentration_weight/nullif(sum(concentration_weight) OVER(PARTITION BY fiscal_year),0) AS share,
 row_number() OVER(PARTITION BY fiscal_year ORDER BY concentration_weight DESC,recipient_id) AS rnk
 FROM recipient_year
), parents AS (
 SELECT fiscal_year,sum(pow(share,2))*10000 AS parent_hhi
 FROM (SELECT *,concentration_weight/nullif(sum(concentration_weight) OVER(PARTITION BY fiscal_year),0) AS share FROM parent_year)
 GROUP BY fiscal_year
)
SELECT fiscal_year, sum(pow(share,2))*10000 AS hhi,
 sum(share) FILTER(WHERE rnk<=4) AS top4_share,
 sum(concentration_weight) AS concentration_denominator,
 count(*) FILTER(WHERE concentration_weight>0) AS positive_net_recipients,
 max(parent_hhi) AS parent_hhi
FROM shares JOIN parents USING(fiscal_year) GROUP BY fiscal_year;

CREATE OR REPLACE VIEW annual_summary AS
WITH totals AS (
 SELECT fiscal_year,sum(obligation) AS net_obligations,sum(positive_obligation) AS positive_obligations,
 sum(CASE WHEN obligation<0 THEN obligation ELSE 0 END) AS negative_obligations,
 count(*) AS transactions,count(DISTINCT award_id) AS awards,count(DISTINCT recipient_id) AS recipients,
 count(*) FILTER(WHERE obligation<0) AS negative_transactions,
 count(*) FILTER(WHERE competition_missing) AS missing_competition_transactions,
 coalesce(sum(positive_obligation) FILTER(WHERE is_competed),0)/nullif(sum(positive_obligation),0) AS competition_share,
 coalesce(sum(positive_obligation) FILTER(WHERE competition_missing),0)/nullif(sum(positive_obligation),0) AS missing_competition_share,
 coalesce(sum(positive_obligation) FILTER(WHERE month(action_date)=9),0)/nullif(sum(positive_obligation),0) AS september_share,
 count(*) FILTER(WHERE offers_received IS NULL) AS missing_offers_transactions,
 count(*) FILTER(WHERE is_competed AND offers_received=1) AS single_offer_competed_transactions,
 count(*) FILTER(WHERE is_competed AND offers_received IS NOT NULL) AS known_offer_competed_transactions
 FROM fact_transactions GROUP BY fiscal_year
)
SELECT * FROM totals JOIN annual_concentration USING(fiscal_year) ORDER BY fiscal_year;

-- Peer grain is fiscal year x NAICS three-digit subsector, NOT all recipients ranked by raw dollars.
CREATE OR REPLACE VIEW peer_competition AS
WITH base AS (
 SELECT fiscal_year,substring(naics,1,3) AS naics3,
 count(*) AS transactions,count(DISTINCT award_id) AS awards,count(DISTINCT recipient_id) AS recipients,
 sum(obligation) AS net_obligations,sum(positive_obligation) AS positive_obligations,
 coalesce(sum(positive_obligation) FILTER(WHERE is_competed),0)/nullif(sum(positive_obligation),0) AS competition_share,
 count(*) FILTER(WHERE competition_missing) AS missing_competition_transactions,
 count(*) FILTER(WHERE offers_received IS NULL) AS missing_offers_transactions,
 count(*) FILTER(WHERE is_competed AND offers_received=1) AS single_offer_competed_transactions,
 count(*) FILTER(WHERE is_competed AND offers_received IS NOT NULL) AS known_offer_competed_transactions,
 coalesce(sum(positive_obligation) FILTER(WHERE month(action_date)=9),0)/nullif(sum(positive_obligation),0) AS september_share
 FROM fact_transactions GROUP BY fiscal_year,substring(naics,1,3)
), weights AS (
 SELECT fiscal_year,substring(naics,1,3) AS naics3,recipient_id,greatest(sum(obligation),0) AS weight
 FROM fact_transactions GROUP BY fiscal_year,substring(naics,1,3),recipient_id
), hhi AS (
 SELECT fiscal_year,naics3,sum(pow(share,2))*10000 AS hhi
 FROM (SELECT *,weight/nullif(sum(weight) OVER(PARTITION BY fiscal_year,naics3),0) AS share FROM weights)
 GROUP BY fiscal_year,naics3
)
SELECT base.*,hhi.hhi,base.awards>=5 AS adequate_peer_size,
 single_offer_competed_transactions::DOUBLE/nullif(known_offer_competed_transactions,0) AS single_offer_rate
FROM base LEFT JOIN hhi USING(fiscal_year,naics3);

-- "Entry" and "exit" mean observed in this cohort, not entry/exit from the federal market.
CREATE OR REPLACE VIEW recipient_entry_exit AS
WITH bounds AS (
 SELECT recipient_id,min(fiscal_year) AS first_observed_year,max(fiscal_year) AS last_observed_year
 FROM recipient_year GROUP BY recipient_id
)
SELECT ry.*,bounds.first_observed_year,bounds.last_observed_year,
 ry.fiscal_year=bounds.first_observed_year AS first_year_observed,
 ry.fiscal_year=bounds.last_observed_year AS last_year_observed,
 lag(ry.net_obligations) OVER(PARTITION BY ry.recipient_id ORDER BY ry.fiscal_year) AS previous_observed_year_obligations
FROM recipient_year ry JOIN bounds USING(recipient_id);

CREATE OR REPLACE VIEW monthly_patterns AS
SELECT fiscal_year,month(action_date) AS calendar_month,
 count(*) AS transactions,count(DISTINCT award_id) AS awards,
 sum(obligation) AS net_obligations,sum(positive_obligation) AS positive_obligations,
 sum(CASE WHEN obligation<0 THEN obligation ELSE 0 END) AS negative_obligations
FROM fact_transactions GROUP BY fiscal_year,month(action_date);

CREATE OR REPLACE VIEW composition AS
SELECT fiscal_year,substring(naics,1,3) AS naics3,psc,agency_name,subagency_name,
 count(*) AS transactions,count(DISTINCT award_id) AS awards,
 sum(obligation) AS net_obligations,sum(positive_obligation) AS positive_obligations
FROM fact_transactions GROUP BY ALL;
