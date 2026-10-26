select * from {{ ref('peer_award_year') }}
where single_offer_competed_award_years>known_offer_competed_award_years
or known_offer_competed_award_years>competed_award_years
or competed_award_years>award_years
or missing_competition_award_years>award_years
or single_offer_rate<0 or single_offer_rate>1
