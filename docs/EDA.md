# NRC procurement: evidence and sensitivity

This is the full downloaded cohort of 4,683 reported contract actions across 1,588 awards and 537 recipient UEIs, FY2022–FY2024. It is a current-source retrospective snapshot, not a reconstruction of what the database showed in each historical year.

## Accounting and a heavy-tailed portfolio

Net obligations are $548,751,367.35: $566,728,702.87 of positive commitments plus $-17,977,335.52 of deobligations. There are 582 negative, 1,294 zero and 2,807 positive actions. Removing negatives would overstate net spending. Obligations are commitments, not outlays, realized costs or ceilings.

Among positive actions, median obligation is $61,844.00, the 90th percentile is $430,985.40, the 99th percentile is $2,443,728.70, and the maximum is $13,174,043.43. The top ceil(1% × 2807) positive actions account for 21.1% of positive commitments. This tail makes averages and raw-total rankings poor peer comparisons.

## Annual composition

| FY | Net obligations | Positive commitments | Awards | September share of positive commitments | Recipient HHI |
|---|---:|---:|---:|---:|---:|
| 2022 | $172,539,161.85 | $178,876,473.04 | 836 | 23.6% | 441.5 |
| 2023 | $183,288,400.22 | $189,813,830.66 | 799 | 10.1% | 438.3 |
| 2024 | $192,923,805.28 | $198,038,399.17 | 799 | 15.0% | 383.2 |

HHI is 10,000 × sum(positive recipient-year net balance share²) within fiscal year. Negative recipient-year net balances receive zero HHI weight; all signed actions remain in net totals. The same signed-net totals reconcile with the official transaction-level aggregate. See `data/processed/validation.json` and the retrieval manifest for filters and source receipt hashes.

## What is being bought

| NAICS | Description | Positive-obligation share | Awards |
|---|---|---:|---:|
| 541519 | OTHER COMPUTER RELATED SERVICES | 29.9% | 435 |
| 541512 | COMPUTER SYSTEMS DESIGN SERVICES | 15.7% | 40 |
| 541511 | CUSTOM COMPUTER PROGRAMMING SERVICES | 14.0% | 61 |
| 511210 | SOFTWARE PUBLISHERS | 4.1% | 31 |
| 541690 | OTHER SCIENTIFIC AND TECHNICAL CONSULTING SERVICES | 4.0% | 148 |
| 541611 | ADMINISTRATIVE MANAGEMENT AND GENERAL MANAGEMENT CONSULTING SERVICES | 3.7% | 72 |
| 561210 | FACILITIES SUPPORT SERVICES | 3.5% | 12 |
| 541330 | ENGINEERING SERVICES | 2.4% | 53 |
| 517110 | WIRED TELECOMMUNICATIONS CARRIERS | 2.3% | 7 |
| 541715 | RESEARCH AND DEVELOPMENT IN THE PHYSICAL, ENGINEERING, AND LIFE SCIENCES (EXCEPT NANOTECHNOLOGY AND BIOTECHNOLOGY) | 1.8% | 28 |
| 541990 | ALL OTHER PROFESSIONAL, SCIENTIFIC, AND TECHNICAL SERVICES | 1.4% | 61 |
| 334111 | ELECTRONIC COMPUTER MANUFACTURING | 1.3% | 19 |

These are industry classifications, not interchangeable purchases. Even within an industry, contract size, complexity, vehicle and legally permitted procedures can differ.

## Competition and missingness

19 of 4683 action records have no classified competition status; 1319 lack a usable offer count. Unknown values do not become noncompetitive or single-offer observations. 0 records lack a parent UEI. Every action has a recipient UEI.

Peer comparisons use the latest observed action per award and fiscal year, with deterministic action-date/revision/key ordering. This prevents a frequently modified award from counting as many separate competitions. It remains a reporting proxy because a modification is not necessarily a new competition. A single-offer denominator includes only competitive award-year observations with a positive reported offer count. See `analysis.json` for every numerator and denominator.

## Entity grouping changes the question

106 recipient UEIs have more than one reported parent identifier across the window. This can reflect reorganization, correction, reporting conventions or ownership changes; the snapshot alone cannot distinguish them. We retain the action-level attribute history instead of silently backdating the latest parent.

| Grouping convention | FY2022 HHI | FY2023 HHI | FY2024 HHI |
|---|---:|---:|---:|
| recipient_uei | 441.5 | 438.3 | 383.2 |
| parent_reported_on_action | 444.0 | 439.7 | 370.4 |
| latest_observed_parent | 443.1 | 439.7 | 384.4 |

These scenarios are explicit alternative definitions, not posterior uncertainty intervals. UEI resolves legal-recipient identity; parent aggregation asks a broader question. Fuzzy name matching must not overwrite conflicting UEIs.

## Statistical stability of the year-end pattern

This cohort is a census of the selected records, so a sampling confidence interval for its exact total is inappropriate. We instead resample entire awards with replacement within each FY, preserving their action histories. The 2.5th–97.5th percentile range across 1,000 replicates describes how September's positive-obligation share responds to portfolio composition. Seed: 20261025.

| FY | Award clusters | Award-mix resampling range |
|---|---:|---:|
| 2022 | 836 | 17.5%–30.3% |
| 2023 | 799 | 5.7%–16.2% |
| 2024 | 799 | 10.2%–21.0% |

This does not identify a causal year-end effect. It does not model reporting error or unobserved contracts. Look at individual timelines and peers before making a decision.

## Reproduction and boundaries

Run `python -m civicledger.reports` after acquisition/warehouse build. Every value above is emitted to `data/reports/analysis.json` from SQL in `civicledger/reports.py`. Data are limited to the awarding agency, contract types and action-date range in the manifest. Grants, subawards, IDVs, spending by other agencies and actions outside the window are excluded. Award counts are window activity counts; entry and exit are observed within-window presence, not business formation or market withdrawal.

The [three analytical case studies](CASE_STUDIES.md) link directly to the original award records. The separate [linkage study](LINKAGE.md) evaluates identity masking and review allocation; it is not a misconduct detector.
