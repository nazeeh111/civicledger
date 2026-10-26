# Warehouse and source contract

The release snapshot covers **4,683 NRC-awarded prime contract transaction actions**, all sectors and contract types A/B/C/D, with action dates 2021-10-01 through 2024-09-30 (FY2022–FY2024). A federal fiscal year starts October 1. This is a bounded procurement cohort, not all federal spending, and it excludes IDV vehicles, grants and subawards.

## Acquisition and replay

Run `python -m civicledger.ingest` to request a fresh immutable source snapshot. It records exact filters, source count, official transaction-level annual aggregates, download receipt, status responses, original ZIP/CSV digests, retrieval timestamps and the public projection digest. Existing raw directories are never reused. Long-running bulk jobs can resume with `--resume /path/to/download_request_receipt.json`. Failure to match the official count stops processing instead of silently publishing a partial cohort.

`data/processed/manifest.json` describes snapshot `20261026T015420Z`. Its full ZIP and original CSV are retained locally under `data/raw/20261026T015420Z/`, which is excluded from public release because the bulk source includes unneeded contact/address fields. The public `transactions.csv` preserves 52 selected source columns. Four descriptions containing an email address or telephone pattern are omitted **in full** so that named contacts are removed with their contact information. The raw original bytes are unchanged. This is recorded as a transformation, not represented as an untouched raw export.

`data/processed/source_contracts.json` pins the inspected USAspending implementation and API contracts to source commit `0a6d86a1e7e4105f349ec5db193ed4c7fca00466` with file digests. This pins inspected source, not the production service's undisclosed deployment version.

The source's transaction key is `contract_transaction_unique_key`; award key is `contract_award_unique_key`. Each row carries `last_modified_date` and `initial_report_date`. A new retrieval may revise an existing transaction's values. Historical snapshots are retained, but this first release does not claim to reconstruct every revision made before retrieval. `source_last_modified` is the latest supplied source timestamp, not a complete revision event log.

## Accounting and grain

- **Action obligation** is incremental funding committed by a transaction. Negative values are legitimate deobligations. The signed sum reconciles exactly with official transaction aggregates under identical filters and spending level.
- **Outlays** are cash disbursements. The official annual response has null outlays for this cohort. The app does not substitute obligations for outlays.
- **Award totals and ceilings** are stock-like reported values. They can repeat across modifications. The warehouse stores them separately and chooses the latest in-cohort report per award. It never sums these fields across transaction rows.
- **Modifications** can exercise options, fund increments, correct records or deobligate funds. A source modification identifier and transaction number are preserved. Zero obligations can still be meaningful actions.
- **Award history** begins at the first observed action in this cohort, which may be later than award inception. `cumulative_in_cohort_obligation` is deliberately named for this limit. Sort ties are resolved deterministically by source modification timestamp and transaction key; this is not proof of the order of same-day legal actions.
- **Recipients** use UEI first. All 4,683 rows in this cohort have a UEI. DUNS is mostly missing after the identifier transition and is retained for provenance and evaluation, not used as an excuse to merge similar names. Legal entities and reported parent groups answer different questions.
- **Parent attributes** are preserved per action. A supplier can report several parents during the window. These may reflect corporate changes or reporting corrections; they are not verified ultimate beneficial ownership.

`dim_recipient_history` stores one observed recipient attribute bundle per key with first/last observation dates. Facts join directly to this bundle key, preserving the exact name/location/parent attributes supplied on each action. These are observation intervals, not asserted legal effective-date ranges. `dim_agency` and `dim_classification` preserve observed code/description combinations. `mart_awards` has exactly one row per award; `award_timeline` remains transaction grain.

## Metric conventions

Default concentration uses `w = max(sum(action obligation) per recipient-year, 0)`; share is `w/sum(w)` and HHI is `10000*sum(share²)`. Negative recipient-year balances remain in signed net totals and receive zero concentration weight. The concentration denominator is explicitly exported and differs from total net obligations when some suppliers have negative annual balances. This is an allocation statistic within the selected agency, not a competition-law market definition or risk threshold.

Positive action obligations are a separate gross flow. Competition and September shares use this gross denominator so that negative reversals cannot make percentages negative or greater than one. These gross shares must not be confused with the positive-net HHI convention.

Competed codes are A (full and open), D (full and open after exclusion) and F (competed under simplified acquisition procedures). Unknown code rows remain unknown. Single-offer rates use only competed records with a known offer count and publish both numerator and denominator. A null denominator yields null; an observed zero numerator yields zero.

The core `peer_competition` view describes **action records**, which can repeat competition/offer attributes across modifications. The dbt `analytics.competition_award_year` and `analytics.peer_award_year` models provide the companion **unique award-year** view using the latest observed attributes per award-year. They expose counts of award-years with changed competition/offer reports. Neither view represents individual tender rounds. Peers are FY × three-digit NAICS; at least five distinct observed awards are required before the app calls a peer group adequate. This is a display rule, not an inferential power guarantee.

## Build and evidence

Run `python -m civicledger.warehouse` to build `data/warehouse.duckdb`, native SQL marts, validation, CSV projections, profiles and `app/dist/data.json` from the public minimized snapshot.

From the repository root, run:

```sh
CIVICLEDGER_DB="$PWD/data/warehouse.duckdb" dbt build --project-dir dbt --profiles-dir dbt
pytest tests/test_warehouse.py
```

The dbt models add supplier cohorts and year-over-year windows, one-row-per-award-year competition reports, peer denominators and source revision lag. Native SQL validation checks transaction and history keys, grain-preserving joins, cumulative endpoint accounting, boundaries, fiscal dates, missingness conventions, signed-flow identities and official aggregate reconciliation. Python tests add privacy/provenance checks and a visibly synthetic +100/−40/0/+40 accounting fixture. Synthetic fixture results are not analytical findings.

At the checked snapshot, 17 native SQL checks, 15 dbt data tests and six warehouse Python tests passed. Official net obligations reconcile to the cent: FY2022 $172,539,161.85; FY2023 $183,288,400.22; FY2024 $192,923,805.28. Persisted machine-readable evidence is in `data/processed/validation.json` and `dbt_validation.json`.
