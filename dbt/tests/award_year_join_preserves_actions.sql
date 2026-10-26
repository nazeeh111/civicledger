select sum(action_records) as a,(select count(*) from {{ source('warehouse','fact_transactions') }}) as b
from {{ ref('competition_award_year') }} having a<>b
