select fiscal_year,count(*) as transaction_records,
 median(date_diff('day',action_date,cast(source_last_modified as date))) as median_days_action_to_last_modified,
 quantile_cont(date_diff('day',action_date,cast(source_last_modified as date)),0.95) as p95_days_action_to_last_modified,
 count(*) filter(where date_diff('day',action_date,cast(source_last_modified as date))>365) as revised_more_than_year_after_action
from {{ source('warehouse','fact_transactions') }} group by fiscal_year
