with award_flows as (
 select fiscal_year,award_id,sum(obligation) as net_obligations,
  sum(positive_obligation) as positive_obligations,count(*) as action_records,
  count(distinct competition_code) as competition_codes_observed,
  count(distinct offers_received) as offer_counts_observed
 from {{ source('warehouse','fact_transactions') }} group by fiscal_year,award_id
), latest as (
 select *,row_number() over(partition by fiscal_year,award_id order by action_date desc,source_last_modified desc,transaction_id desc) as rn
 from {{ source('warehouse','fact_transactions') }}
)
select concat(f.award_id,':',f.fiscal_year) as award_year_key,f.*,l.recipient_id,l.recipient_name,
 substring(l.naics,1,3) as naics3,l.competition_code,l.competition,l.offers_received,l.source_url,
 coalesce(l.competition_code in ('A','D','F'),false) as is_competed,
 l.competition_code is null as competition_missing,
 l.transaction_id as latest_observed_transaction_id
from award_flows f join latest l using(fiscal_year,award_id) where l.rn=1
