with balances as (
 select *,sum(concentration_weight) over(partition by fiscal_year) as denominator,
  lag(fiscal_year) over(partition by recipient_id order by fiscal_year) as previous_observed_fy,
  lag(net_obligations) over(partition by recipient_id order by fiscal_year) as previous_observed_net,
  min(fiscal_year) over(partition by recipient_id) as first_observed_fy,
  max(fiscal_year) over(partition by recipient_id) as last_observed_fy
 from {{ source('warehouse','recipient_year') }}
)
select concat(recipient_id,':',fiscal_year) as recipient_year_key,*,
 concentration_weight/nullif(denominator,0) as positive_net_share,
 case when previous_observed_fy=fiscal_year-1 then net_obligations-previous_observed_net end as yoy_net_change,
 dense_rank() over(partition by fiscal_year order by concentration_weight desc) as annual_rank
from balances
