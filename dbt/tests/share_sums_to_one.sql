select fiscal_year,sum(positive_net_share) as share
from {{ ref('recipient_cohorts') }} group by fiscal_year having abs(sum(positive_net_share)-1)>0.000000001
