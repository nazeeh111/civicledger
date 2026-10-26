# CIVICLEDGER explorer

The app is a buildless, browser-local explorer of the retained public snapshot. Serve `dist/` with any static server. No accounts, API keys, analytics, package installation, or server-side database are needed to explore the published data. Fonts are bundled with their open licenses.

```sh
python3 -m http.server 8080 --directory app/dist
```

The warehouse exports `dist/data.json`; the linkage analysis exports `dist/linkage.json`; the statistical report supplies `dist/reports.json` and `dist/cases.json`. The app does not fetch current USAspending records at runtime. Official evidence links open the public source record.

## Verification

```sh
node --check app/dist/app.js
node app/check-data.mjs
```

The aggregation check initializes the actual current app code against the published snapshot in a minimal DOM environment. It checks annual net obligations, HHI, top-four shares, competition classification, historical recipient attribution, fixed-scope case dossiers, and one-at-a-time conditional identity previews. It is not a substitute for browser layout and interaction checks.

## Interpretation

Fiscal-year controls filter the transaction ledger and recipient totals. Fixed analytical cases, full-cohort statistical working papers, and the identifier-masked research experiment retain their explicitly labeled scopes. A case dossier always contains the complete case cohort, independently of hidden explorer filters, so its denominator and cited evidence can be reproduced.

A recipient ledger includes any award with an action attributed to that recipient. For awards that change recipient, the row shows attributed amounts and actions; the full award detail preserves the recipient reported on every transaction. Cumulative amounts begin at the retained window boundary, not award inception.

Identity controls preview one conditional pair decision at a time over the model's consistent partitions, with other components unresolved. Selecting another preview clears the first. Conditional HHI means and modal sampled review rankings are not additive pairwise effects or a joint adjudicated partition. The operational review queue remains empty when reliable source identifiers resolve the cohort; masked-identifier experiments remain visibly separate.

Public descriptions are the warehouse's minimized export. Full-field raw archives remain local; the release retains retrieval metadata, source checksums, and acquisition code.
