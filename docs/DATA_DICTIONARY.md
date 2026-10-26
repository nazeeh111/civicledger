# Data dictionary and interpretation

The public snapshot has 52 selected columns from USAspending's prime-contract transaction CSV. Empty source cells become SQL nulls. The publication manifest lists every included and excluded source column, original and public digests, and transformations. Each source fact has one `contract_transaction_unique_key`; it is not one row per award.

| Source fields | Warehouse interpretation |
|---|---|
| `contract_transaction_unique_key` | `transaction_id`, unique within this retrieved snapshot |
| `contract_award_unique_key`, `award_id_piid` | `award_id` identifies the award; PIID is the displayed procurement identifier and should not be treated as globally unique by itself |
| `modification_number`, `transaction_number` | Source action identifiers; preserve strings, including zeros and alphanumeric modifications |
| `parent_award_agency_id`, `parent_award_id_piid` | Contract vehicle references; an IDV vehicle is not an additional obligation to add to this cohort |
| `federal_action_obligation` | Signed incremental commitment, DECIMAL(20,2); sum this field for transaction spending |
| `total_dollars_obligated` | Reported award-level stock, stored separately; never sum repeated values across modifications |
| `current_total_value_of_award`, `potential_total_value_of_award` | Reported current/potential award values, not cash paid or incremental commitments; latest in-window report retained in the award mart |
| `action_date`, `action_date_fiscal_year` | Action date and federal FY; FY runs October 1 to September 30; inclusion uses action date |
| `period_of_performance_start_date`, `period_of_performance_current_end_date` | Reported performance boundaries; not tender publication or bid submission dates |
| `awarding_agency_code/name`, `awarding_sub_agency_code/name`, `awarding_office_code/name` | Agency issuing the award, plus subagency and office, as reported on each action |
| `funding_agency_code/name` | Agency supplying funds, which can differ from the awarding agency; scope is based on awarding agency |
| `recipient_uei`, `recipient_duns` | Reliable recipient identifiers; UEI is complete in the release, DUNS can be absent. IDs are preserved as strings |
| `recipient_name`, `recipient_doing_business_as_name` | Reported organization name/alias; similar or equal names do not override different UEIs |
| `recipient_parent_uei/duns/name` | Reported parent attributes at each action; distinct from legal-recipient identity and unverified as beneficial ownership |
| `recipient_city_name`, `recipient_state_code`, `recipient_country_code` | Coarse public location features for linkage; no street, ZIP, telephone or fax columns published |
| `naics_code/description` | Industry classification, not a product/bid inventory; core peers use FY × first three NAICS digits, EDA also reports six-digit composition |
| `product_or_service_code/description` | Product/service classification, with observed labels retained |
| `award_type_code`, `award_type` | A/B/C/D prime contract actions; this cohort excludes IDVs, grants and subawards |
| `type_of_contract_pricing_code`, `type_of_contract_pricing` | Reported contract pricing arrangement; can provide ordinary context for changes |
| `extent_competed_code`, `extent_competed` | A/D/F classified as competed; B/C/G/NDO as noncompetitive. Missing/unknown values remain separate |
| `number_of_offers_received` | Nullable reported count; modifications can repeat it. Not a list of bidders or distinct tender rounds |
| `solicitation_procedures_code`, `solicitation_procedures` | Reported procedure category; does not provide tender timing |
| `type_of_set_aside_code`, `type_of_set_aside` | Reported set-aside category, a possible lawful explanation for restricted competition |
| `transaction_description` | Public purpose/context text, except whole contact-bearing descriptions omitted under the documented rule |
| `last_modified_date`, `initial_report_date` | Supplied source timestamps. Current-snapshot metadata, not a complete sequence of database revisions |
| `usaspending_permalink` | Direct official award evidence link. Its live contents can be revised and include lifetime values outside this cohort |

## Derived grains

- `positive_obligation`: max(incremental action obligation, 0), used for gross-flow composition, competition exposure and September shares.
- `recipient_year.concentration_weight`: max(sum(signed actions within recipient-year), 0), used for HHI and top-four share. Net-negative recipients are still in signed totals.
- `recipient_history_id`: a hash of the observed UEI/name/parent/location attribute bundle. It joins facts to one observed bundle without duplicating transactions. First/last observation is not a verified legal validity interval.
- `mart_awards`: one row per award, sums only incremental in-window action flows, then attaches a deterministic latest in-window report of stock/attributes. Six awards have more than one recipient UEI over the observation window, so recipient drilldown must use action attribution rather than attaching the entire award to its latest recipient.
- `award_timeline.cumulative_in_cohort_obligation`: running signed sum ordered by action date, source last-modified timestamp and transaction key. Same-day ordering is a deterministic display convention.
- `analytics.competition_award_year`: one latest observation per award and FY, plus flow aggregates and report-change indicators; source modifications are not counted as separate competitions in this companion view.
- `data/linkage/*features.csv`: identifier-masked model features kept apart from label files. Labels use held-out UEI equality as an imperfect reference for legal-recipient identity.

## Unavailable values

Cash outlays are not available at the action grain used here. Tender start/deadline dates, individual bid prices, rejected bidders, evaluation decisions, adjudicated misconduct and verified ultimate ownership are unavailable. Nulls for these concepts must not be replaced with zero, false, a date derived from an award action, or an invented risk score.
