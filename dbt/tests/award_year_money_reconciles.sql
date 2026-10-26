select a.fiscal_year,a.net_obligations,sum(b.net_obligations) as award_net
from {{ source('warehouse','annual_summary') }} a
join {{ ref('competition_award_year') }} b using(fiscal_year)
group by a.fiscal_year,a.net_obligations
having a.net_obligations<>sum(b.net_obligations)
