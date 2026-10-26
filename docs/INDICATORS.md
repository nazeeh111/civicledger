# What the source can support

CIVICLEDGER studies reported procurement patterns. A pattern is a reason to check records or ask a question, never a finding of misconduct. There are no adjudicated misconduct labels here and no fraud-detection accuracy measure.

USAspending contract transactions are not Open Contracting Data Standard (OCDS) releases. We inspected [Cardinal's implementation](https://github.com/open-contracting/cardinal-rs/tree/0b28400d90e0167ff671c5d0b616418b4ac6dc2e/src/indicators) and the [Open Contracting Partnership methodology](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/) before selecting measures. We do not convert missing tender fields into negative findings.

| Measure | Required evidence | Status in this release |
|---|---|---|
| Recipient concentration | Signed transaction obligations, recipient identifiers, a defined cohort | Supported, with positive recipient-year net balance shares and separately reported signed net totals |
| Reported competitive procedures | Extent-competed code, action date, peer category | Supported where source codes are known; unknown remains unknown |
| Reported single offer | Number of offers received and competitive-procedure code | Descriptive proxy only. A reported offer count is not a complete tenderer/bid table; transaction modifications are not independent competitions |
| Fiscal year-end obligations | Action date, signed obligation | Supported descriptively. September is a calendar window, not evidence of evasion or waste |
| Modification activity | Transaction identity, award identity, modification number, action date | Supported within FY2022–24; pre-window history is left-censored |
| Short tender window (Cardinal R003) | Tender publication/start and submission deadline | Unavailable. Award/action dates cannot substitute |
| Small bid-price gaps / heavily discounted bid (R024/R058) | All valid bids, amounts, winning bid, selection rules | Unavailable. An obligation or award ceiling is not a bid price |
| Repeated losing bidders (R025) | Unsuccessful bidders across tenders | Unavailable. USAspending reports award recipients |
| Identical submitted prices (R028) | Multiple tenderers and submitted prices | Unavailable |
| Late winning bid (R030) | Bid submission timestamps and tender deadline | Unavailable |
| Disqualification patterns (R035/R036/R038) | Submitted bids, eligibility decisions, award criteria | Unavailable |
| Item-category breadth (R048) | Awarded line items with consistent category hierarchy | Not implemented as Cardinal R048. NAICS is an industry classification, not a full item inventory |

## Reading the measures

Concentration is the Herfindahl–Hirschman index (HHI): sum of squared positive recipient-year net balance shares, multiplied by 10,000. A higher number means more exposure concentrated in fewer recipients in this cohort. It does not identify the reason. Technical specialization, continuity requirements, lawful set-asides, procurement vehicles and agency mission can all affect concentration and competition.

HHI uses `greatest(sum(obligation), 0)` after grouping by recipient and fiscal year, divided by the sum of these nonnegative balances. Net-negative recipients receive zero HHI weight. Signed net obligations, negative amounts and counts are always retained and separately reported. Competition and September exposure shares instead use gross positive action obligations, `sum(greatest(obligation,0))`. These are different denominators and remain explicitly labeled. Neither is cash paid or total contract value.

Competition is compared within fiscal year and NAICS peer groups. Small groups and missing classifications remain visible. An action-weighted rate measures recorded actions; an award-level rate measures distinct awards using a documented observation rule. Neither is a causal effect or an estimate of wrongdoing.

Entity resolution answers whether records refer to the same legal recipient. A shared ultimate parent is a separate analytical grouping. Similar names do not override conflicting reliable identifiers. Grouping subsidiaries by parent can legitimately change concentration, but does not prove common bidding behavior.

## Foundations and versions

The source-contract review records exact upstream revisions in `docs/source-revisions.json`. Cardinal provides the prerequisite audit; it is not executed on a fabricated OCDS conversion. Evidence's SQL-as-report approach informs source-linked query reporting; the explorer uses a small static renderer over tested DuckDB outputs so the demo has no server or credential dependency. Splink supplies the probabilistic linkage baseline, while CIVICLEDGER's decision-sensitive review experiment is evaluated separately.
