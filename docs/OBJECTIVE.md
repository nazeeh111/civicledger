Build and publicly release CIVICLEDGER: an evidence-first public-procurement intelligence platform that reconstructs who receives public contract funding, measures competition and supplier concentration, surfaces unusual patterns, and shows how uncertain entity matches affect conclusions. Deliver deep SQL, EDA, statistical analysis, and an original uncertainty-aware decision workflow, not a fraud-accusation dashboard.\
\
FOUNDATIONS\
\- USAspending API: https\://api.usaspending.gov/\
\- Source implementation/contracts: https\://github.com/fedspendingtransparency/usaspending-api\
\- Probabilistic linkage: https\://github.com/moj-analytical-services/splink\
\- Procurement indicators: https\://github.com/open-contracting/cardinal-rs\
\- Methodology: https\://www\.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/\
\- SQL reporting: https\://github.com/evidence-dev/evidence\
Use DuckDB/dbt for the warehouse. Inspect indicator prerequisites: USAspending is not automatically OCDS, and unavailable tender/bid fields must remain unavailable.\
\
DATA AND SQL. Start with a bounded agency/sector and several complete fiscal years of actual contract transactions. Maintain raw snapshots, retrieval metadata, source IDs, revisions, and source-to-metric lineage. Separate transaction facts from award summaries and recipient/agency/classification dimensions. Explain obligations versus outlays, award ceilings, modifications, deobligations, parent recipients, fiscal dates, and missing competition fields. Do not double-count award totals across modifications or erase legitimate negative obligations.\
\
Implement substantial tested SQL for recipient/agency cohorts, cumulative obligations, modification histories, peer-group competition, concentration indices, entry/exit, and year-end patterns. Use windows, conditional aggregation, multi-grain joins, and history-aware dimensions where supported. Test joins, keys, null handling, metric invariants, and reconciliation with official aggregates using identical filters. Include a compact SQL cookbook and real query-performance analysis.\
\
EDA AND STATISTICS. Investigate heavy-tailed spending, missingness, agency/sector composition, concentration, contract changes, competition patterns, and sensitivity to entity grouping. Separate descriptive associations from causal explanations. Compare peers rather than ranking raw totals as suspicious. Publish clear findings with denominators, uncertainty, alternative explanations, and links to original award records.\
\
ORIGINAL CONTRIBUTION. Use reliable identifiers first; apply probabilistic linkage only where needed. Preserve uncertain matches rather than silently merging businesses with similar names. Develop an uncertainty-aware analysis that recomputes concentration and triage rankings across plausible entity resolutions, then prioritizes which ambiguous matches are most valuable to review because they could change a decision. Account for cluster consistency instead of independently sampling incompatible pairwise matches. This decision-sensitive review strategy is the research contribution to test.\
\
VALIDATION. Benchmark linkage against exact/normalized matching and a probabilistic baseline using held-out identifier-backed entities, masking identifiers without leaking them into features. Evaluate precision/recall, calibration, and error costs. Compare random, uncertainty-only, and decision-sensitive review policies under equal budgets. Measure ranking stability and concentration-estimate sensitivity. Keep synthetic perturbation tests visibly separate from real-data findings. Without adjudicated misconduct labels, never report fraud-detection accuracy; anomalies are review candidates, not evidence of wrongdoing.\
\
EXPERIENCE. Build a money-flow explorer with agency→award→recipient drilldown, peer comparisons, contract timelines, uncertainty-aware entity views, and a review queue. Every number and flag must expose its formula, SQL, evidence, and possible benign explanation. Export a reproducible case dossier and a concise decision memo. Make the demo show whether a conclusion survives ambiguity, not just an impressive graph.\
\
ACCEPTANCE. A rerunnable real-data warehouse; tested SQL; substantive EDA; calibrated linkage evaluation; decision-sensitive review experiments; three source-traceable analytical case studies; usable application and exports; and complete public release. Never publish unnecessary personal information or imply corruption from an unusual pattern.\
\
TOPIC SEEDS: sql, duckdb, dbt, data-analytics, data-science, exploratory-data-analysis, entity-resolution, record-linkage, anomaly-detection, open-data, public-procurement, data-visualization.\
\
Release standard: the acceptance requirements above, as clarified by the user.