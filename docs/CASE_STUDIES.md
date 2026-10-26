# Three source-traceable analytical cases

These are selected observations and review questions, not findings of wrongdoing. The selection rule is disclosed for each case. Source data are in the retrieval manifest's snapshot; the official award page may show later revisions or lifetime totals.

## A large commitment stream needs contract context

How much of the observed portfolio runs through one award?

Selection: Award with largest sum of positive action obligations in the cohort.

Source: [31310018F0052](https://www.usaspending.gov/award/CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100/) · TEKSYNAP CORPORATION.

```json
{
  "award_id": "CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100",
  "piid": "31310018F0052",
  "recipient": "TEKSYNAP CORPORATION",
  "url": "https://www.usaspending.gov/award/CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100/",
  "net": "53852868.10",
  "positive": "56164185.63",
  "actions": 37,
  "first_observed": "2022-01-03",
  "last_observed": "2024-08-14"
}
```

Metric: 9.91% · of cohort positive commitments in this award

Denominator: $566,728,702.87 in positive action obligations across all 4,683 cohort actions; numerator $56,164,185.63 across 37 actions in this award.

Formula: sum(greatest(federal_action_obligation,0)) by award / cohort positive obligations

```sql
with a as (select award_id,sum(positive_obligation) positive from fact_transactions group by 1) select *,positive/sum(positive) over() cohort_share from a order by positive desc limit 1;
```

This is an observed funding stream, not the award ceiling or a cash payment. An existing contract can receive multiple funding actions.

Plausible explanations to check: Agency mission and specialized services; Multi-year funding and option exercises; Use of an established contract vehicle.

Sensitivity and limits: Exact UEIs identify recipients. Parent grouping is a separate sensitivity choice; a large award remains the same award under either convention.

## A negative action is part of the accounting

What changes when reductions in commitments are retained?

Selection: Most negative individual action obligation in the cohort.

Source: [31310018F0052](https://www.usaspending.gov/award/CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100/) · TEKSYNAP CORPORATION.

```json
{
  "transaction_id": "3100_3100_31310018F0052_P00050_NRCHQ1017A0008_0",
  "award_id": "CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100",
  "piid": "31310018F0052",
  "recipient": "TEKSYNAP CORPORATION",
  "url": "https://www.usaspending.gov/award/CONT_AWD_31310018F0052_3100_NRCHQ1017A0008_3100/",
  "action": "2023-05-25",
  "fy": 2023,
  "obligation": "-1335317.53",
  "modification": "P00050"
}
```

Metric: -$1,335,317.53 · signed obligation on the selected modification

Denominator: 4683

Formula: min(federal_action_obligation) across all cohort actions; accounting identity: net = positive + negative obligations

```sql
select transaction_id, obligation from fact_transactions where obligation<0 order by obligation limit 1;
```

A deobligation reduces a prior commitment. It must remain in net totals and timelines. Its size alone cannot establish whether the underlying activity was appropriate.

Plausible explanations to check: Contract closeout and unused balances; A scope or funding correction; Reversal or administrative adjustment.

Sensitivity and limits: The observation window excludes earlier actions. Cumulative amounts begin at the window boundary, not contract inception.

## September commitments invite a timing question

Is the year-end pattern broad or driven by a small number of awards?

Selection: Largest positive September action in the cohort.

Source: [31310022F0089](https://www.usaspending.gov/award/CONT_AWD_31310022F0089_3100_GS35F0889N_4730/) · MCP COMPUTER PRODUCTS INC.

```json
{
  "transaction_id": "3100_4730_31310022F0089_0_GS35F0889N_0",
  "award_id": "CONT_AWD_31310022F0089_3100_GS35F0889N_4730",
  "piid": "31310022F0089",
  "recipient": "MCP COMPUTER PRODUCTS INC",
  "url": "https://www.usaspending.gov/award/CONT_AWD_31310022F0089_3100_GS35F0889N_4730/",
  "action": "2022-09-02",
  "fy": 2022,
  "obligation": "5019795.74",
  "naics_code": "443120",
  "extent_competed": "FULL AND OPEN COMPETITION",
  "number_of_offers_received": "1"
}
```

Metric: 23.6% · September share of FY2022 positive commitments

Denominator: All positive action obligations in FY2022: $178,876,473.04. The linked action is the largest positive September action, shown as context rather than the full numerator.

Formula: September positive obligations / all positive obligations within each fiscal year

```sql
select fiscal_year, sum(case when month(action_date)=9 then greatest(obligation,0) else 0 end)/sum(greatest(obligation,0)) share from fact_transactions group by 1;
```

Compare the annual distribution and award-mix resampling before generalizing. Timing can reflect budget availability and scheduled procurement cycles.

Plausible explanations to check: Fiscal-year funding availability; Scheduled renewal or option dates; A few high-value awards dominating a small cohort.

Sensitivity and limits: Resampling whole awards measures composition stability, not a confidence interval for the observed census or evidence of causality.

The explorer provides each award's in-window action timeline, signed obligation amounts, recipient identifiers and source link. Exported dossiers include the current filters and evidence. A review conclusion should specify what additional records would resolve the question and whether entity grouping would change it.
