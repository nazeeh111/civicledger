with base as (
 select fiscal_year,naics3,count(*) as award_years,sum(action_records) as action_records,
 sum(net_obligations) as net_obligations,
 count(*) filter(where is_competed) as competed_award_years,
 count(*) filter(where competition_missing) as missing_competition_award_years,
 count(*) filter(where is_competed and offers_received is not null) as known_offer_competed_award_years,
 count(*) filter(where is_competed and offers_received=1) as single_offer_competed_award_years,
 count(*) filter(where competition_codes_observed>1 or offer_counts_observed>1) as changed_attributes_award_years
 from {{ ref('competition_award_year') }} group by fiscal_year,naics3
)
select *,single_offer_competed_award_years::double/nullif(known_offer_competed_award_years,0) as single_offer_rate,
 award_years>=5 as adequate_peer_size
from base
