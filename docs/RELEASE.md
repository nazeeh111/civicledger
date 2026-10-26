# CIVICLEDGER 1.0.0 release evidence

Release scope: the acceptance requirements in `OBJECTIVE.md`. Source snapshot `20261026T015420Z`, retrieved October 25, 2026 in America/New_York (October 26 UTC). Public minimized CSV SHA-256: `c0bd912f23dd53a26c0d83c2cd79d0c448959784752fca0a6945f7bdfc84591c`.

## Acceptance map

| Requirement | Delivered artifact and evidence |
|---|---|
| Real-data warehouse, snapshots and lineage | `civicledger/ingest.py`, `warehouse.py`, processed manifest, source-contract digests, local raw originals, public minimized CSV |
| Substantial tested SQL | Native transformations and 17 checks in `sql/`; four dbt analytical models and 15 data tests; SQL cookbook and actual query profiles |
| EDA and statistical analysis | `docs/EDA.md`, `data/reports/analysis.json`; tail distribution, signed accounting, missingness, sector composition, concentration/grouping, year-end award-cluster resampling |
| Calibrated linkage evaluation | `docs/LINKAGE.md`, identifier-disjoint feature/label artifacts, exact/normalized/FS/calibrated baseline metrics, bins, costs and finite-support intervals |
| Decision-sensitive review experiments | Repeated equal-budget policies, coherent partition conditioning, ranking/HHI sensitivity and conditional named top-three conclusions; natural and synthetic evidence separate |
| Three source-traceable cases | `docs/CASE_STUDIES.md`, `data/reports/cases.json`, official award and transaction IDs, formulas and ordinary explanations |
| Application and exports | Static money explorer, action-time recipient drilldown, timelines, peer tables, entity views, experimental queue, downloadable dossier and decision memo |
| Public release | Public source, tagged source archive and public Sites deployment; final links and verification recorded below |

## Verification commands

```sh
uv sync --frozen --extra test
uv run python -m civicledger.reproduce --test
node app/check-data.mjs
```

A separate clean public-source checkout is rebuilt with full default review replicates before publication. This path intentionally lacks local-only raw originals; their provenance check reports a skip while the public projection, recorded source digests, input lineage and accounting checks still run. A normal local run also verifies the retained originals.

The release pipeline fails closed if the input CSV hash differs from the manifest, official annual totals do not reconcile, SQL/dbt tests fail, Splink inference does not reproduce the independent probabilities, or a cached linkage payload belongs to a different source snapshot. `--refresh --skip-linkage` is rejected.

Independent source review identified and resolved inconsistent UI scenario previews, stale linkage reuse, case-export filtering, historical recipient attribution and silent baseline-verification failure. Review found no remaining confirmed release-blocking source issue after corrections. Final clean rebuild and browser/deployment evidence are recorded below.

## Browser evidence

The current-source preview was inspected at desktop and 390-pixel mobile width. Checked flows include overview, fiscal selection, award modifications with negative actions, actual recipient attribution, evidence dialogs, fixed-cohort cases, and downloads. A deobligation dossier downloaded through the UI contains all 4,683 full-cohort source records and its cited transaction even when the explorer was filtered to FY2024. The memo download contains formula, selection, source link, limits and alternative explanations. Copies are retained under `exports/`.

## Material limits

The natural benchmark has only 11 positive pairs and no within-UEI name changes. Exact name matching already solves it. The natural review improvement is small in practical HHI terms and does not change top-three review membership. Synthetic review policies show no advantage at five reviews; eight reference links lie outside scenario support, and a zero scenario width accompanies remaining error. This failure is disclosed rather than treated as certainty.

The source is a current retrospective snapshot, not a full historical revision log. Parent reports are unverified ownership context. Bid-level and tender-time indicators are unavailable. No adjudicated misconduct labels exist, and no fraud-detection claim is made. Public contact minimization uses the documented email/telephone rule and excluded field list; it is not a guarantee about every possible name in public award-purpose text.

## Published endpoints and final checks

- Public explorer: https://civicledger.nazeeh1.chatgpt.site
- Public source: https://github.com/nazeeh111/civicledger
- Versioned release: https://github.com/nazeeh111/civicledger/releases/tag/v1.0.0
- Sites saved version: **2**, source commit `9bf633ef68a13f9190e9d750997c20738a7613ab`.
- Deployment `appgdep_6adeb8ca82e081919c4b898a15e8fb78` returned **succeeded** at 2026-10-26 02:20 UTC (October 25, America/New_York).
- Complete clean public rebuild: **21 Python tests passed, 1 raw-original provenance check explicitly skipped**; 17 SQL checks and 15 dbt data tests passed; both Splink all-pairs runtime checks passed. Local original-preserving run: **22 tests passed**.
- Required public JSON artifacts and CSV/source digests match. The static source exception is tracked explicitly so a machine-wide `dist/` ignore cannot omit the HTML/JS/data from source control.

Machine-readable local/clean-check evidence is in `data/processed/release_validation.json`. Rendered previews are in `docs/screenshots/`. A CI workflow repeats the full public-snapshot rebuild on pushes and pull requests. Final public HTTP, GitHub release and CI outcomes are recorded in the delivered release receipt.
