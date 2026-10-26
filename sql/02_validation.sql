-- Each query returns violated rows. Zero rows = passing. Human labels in warehouse.py map these checks.
-- Not executed as one script; consumed by the warehouse validation runner.
SELECT 'transaction_key_unique' AS test, count(*)-count(DISTINCT transaction_id) AS violations FROM fact_transactions
UNION ALL SELECT 'required_fact_fields',count(*) FROM fact_transactions WHERE transaction_id IS NULL OR award_id IS NULL OR recipient_id IS NULL OR obligation IS NULL OR action_date IS NULL
UNION ALL SELECT 'fiscal_date_consistency',count(*) FROM fact_transactions WHERE fiscal_year <> year(action_date)+CASE WHEN month(action_date)>=10 THEN 1 ELSE 0 END
UNION ALL SELECT 'cohort_boundaries',count(*) FROM fact_transactions WHERE action_date<'2021-10-01' OR action_date>'2024-09-30' OR agency_name<>'Nuclear Regulatory Commission' OR award_type_code NOT IN ('A','B','C','D')
UNION ALL SELECT 'recipient_history_key_unique',count(*)-count(DISTINCT recipient_history_id) FROM dim_recipient_history
UNION ALL SELECT 'history_join_preserves_rows',abs((SELECT count(*) FROM fact_transactions)-(SELECT count(*) FROM fact_transactions f JOIN dim_recipient_history h USING(recipient_history_id)))
UNION ALL SELECT 'history_join_preserves_obligations',CASE WHEN (SELECT sum(obligation) FROM fact_transactions)=(SELECT sum(obligation) FROM fact_transactions f JOIN dim_recipient_history h USING(recipient_history_id)) THEN 0 ELSE 1 END
UNION ALL SELECT 'award_key_unique',count(*)-count(DISTINCT award_id) FROM mart_awards
UNION ALL SELECT 'award_flow_reconciliation',CASE WHEN (SELECT sum(obligation) FROM fact_transactions)=(SELECT sum(net_obligations) FROM mart_awards) THEN 0 ELSE 1 END
UNION ALL SELECT 'signed_flow_identity',count(*) FROM annual_summary WHERE net_obligations<>positive_obligations+negative_obligations
UNION ALL SELECT 'hhi_bounds',count(*) FROM annual_concentration WHERE hhi<0 OR hhi>10000 OR top4_share<0 OR top4_share>1
UNION ALL SELECT 'peer_offer_denominator',count(*) FROM peer_competition WHERE single_offer_competed_transactions>known_offer_competed_transactions
UNION ALL SELECT 'offers_nonnegative',count(*) FROM fact_transactions WHERE offers_received<0
UNION ALL SELECT 'annual_transaction_counts',CASE WHEN (SELECT sum(transactions) FROM annual_summary)=(SELECT count(*) FROM fact_transactions) THEN 0 ELSE 1 END
UNION ALL SELECT 'cumulative_award_endpoint',count(*) FROM (
 SELECT award_id,arg_max(cumulative_in_cohort_obligation,struct_pack(d:=action_date,m:=source_last_modified,t:=transaction_id)) AS cumulative FROM award_timeline GROUP BY award_id
) c JOIN mart_awards a USING(award_id) WHERE c.cumulative<>a.net_obligations;
