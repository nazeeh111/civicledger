# Query performance at the release snapshot

DuckDB 2.0.0, 4,683 transaction rows, local machine. Each query is warmed once, then run seven times on one connection with full result materialization. The machine may have concurrent workloads; timings are observations, not a controlled performance comparison.

| Query | Rows returned | Median ms | Min ms | Max ms |
|---|---:|---:|---:|---:|
| annual_concentration | 3 | 10.44 | 8.75 | 12.01 |
| award_timelines | 1,588 | 8.81 | 7.20 | 16.76 |
| peer_competition | 49 | 16.53 | 12.13 | 20.80 |
| history_join | 534 | 3.24 | 2.75 | 10.61 |

Every exact query is in `data/processed/performance.json`; its `EXPLAIN ANALYZE` plan is retained as `profile_<query>.txt`. The build regenerates these measurements.

Concentration first aggregates 4,683 action rows into recipient-year balances, then uses partitioned sums and ranking windows. This reduces the data passed into concentration windows and avoids a supplier-to-award cross product. Award timelines partition and sort by award and date; their cumulative sums must still operate at transaction grain. The history join uses the unique observed attribute-bundle key, preserving all facts and dollars. Peer metrics aggregate at FY × NAICS3 before joining concentration denominators.

The retained plans show sequential scans, hash grouping/joins and window operators. For this cohort a columnar scan is cheap and no index is justified. The dbt award-year model materializes the latest-record selection and action aggregation once for downstream peer analysis; that changes the reporting grain deliberately and is not presented as a speed comparison with action-grain metrics.

The large min/max spread warns against small speedup claims under concurrent laptop load. These observations establish that this bounded local workflow is interactive. They do not establish performance at federal-wide scale, ingestion throughput, multi-user server latency or superiority to another database.
