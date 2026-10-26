"""Reproducible census EDA, award-mix stability and three source-linked cases.

Run from project root: python -m civicledger.reports
No population confidence intervals are asserted for this fully observed cohort.
"""
from __future__ import annotations

import json
from pathlib import Path
import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path = ROOT) -> dict:
    out = root / "data/reports"
    out.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect()
    c.execute("create table raw as select * from read_csv(?,all_varchar=true)", [str(root / "data/processed/transactions.csv")])
    c.execute("""create table t as select *,
        cast(federal_action_obligation as decimal(20,2)) as obligation,
        greatest(cast(federal_action_obligation as decimal(20,2)),0) as exposure,
        cast(action_date_fiscal_year as int) as fy,
        cast(action_date as date) as action,
        coalesce(nullif(recipient_parent_uei,''),recipient_uei) as reported_parent,
        case when extent_competed_code in ('A','D','E','F') then true
             when extent_competed_code in ('B','C','G','NDO') then false
             else null end as competitive
        from raw""")

    def rows(sql):
        r = c.execute(sql)
        return [dict(zip([x[0] for x in r.description], row)) for row in r.fetchall()]

    overview = rows("""select count(*) transactions, count(distinct contract_award_unique_key) awards,
        count(distinct recipient_uei) recipients, count(distinct naics_code) industries,
        sum(obligation) net, sum(exposure) positive, sum(least(obligation,0)) negative,
        count(*) filter(where obligation<0) negative_actions,
        count(*) filter(where obligation=0) zero_actions,
        count(*) filter(where obligation>0) positive_actions,
        count(*) filter(where competitive is null) missing_competition,
        count(*) filter(where try_cast(number_of_offers_received as int) is null) missing_offers,
        count(*) filter(where recipient_parent_uei is null or recipient_parent_uei='') missing_parent
        from t""")[0]
    annual = rows("""with s as (select fy, recipient_uei, greatest(sum(obligation),0) e from t group by 1,2),
        h as (select fy,sum(pow(e/total,2))*10000 hhi from
            (select *,sum(e) over(partition by fy) total from s) group by fy)
        select t.fy,count(*) actions,count(distinct contract_award_unique_key) awards,
        count(distinct recipient_uei) recipients,sum(obligation) net,sum(exposure) positive,
        sum(exposure) filter(where month(action)=9)/sum(exposure) september_positive_share,
        sum(exposure) filter(where competitive)/sum(exposure) competitive_positive_share,
        any_value(h.hhi) hhi from t join h on t.fy=h.fy group by t.fy order by t.fy""")
    tails = rows("""with ranked as (select exposure,row_number() over(order by exposure desc) rn,
        count(*) over() n from t where exposure>0)
        select count(*) n_positive,quantile_cont(exposure,.5) median,
        quantile_cont(exposure,.9) p90,quantile_cont(exposure,.99) p99,max(exposure) maximum,
        sum(exposure) filter(where rn<=ceil(n*.01))/sum(exposure) top_one_percent_share
        from ranked""")[0]
    composition = rows("""select naics_code,any_value(naics_description) description,count(*) actions,
        count(distinct contract_award_unique_key) awards,sum(exposure) positive,sum(obligation) net,
        sum(exposure)/sum(sum(exposure)) over() share
        from t group by 1 order by positive desc limit 12""")
    # A deterministic latest-observed row per award-year prevents repeated modifications
    # from masquerading as independent competitions.
    c.execute("""create table ay as select * exclude(rn) from (select *,row_number() over(
        partition by contract_award_unique_key,fy order by action desc,last_modified_date desc,
        contract_transaction_unique_key desc) rn from t) where rn=1""")
    peers = rows("""select fy,naics_code,any_value(naics_description) description,count(*) awards,
        count(*) filter(where competitive is not null) known_competition,
        count(*) filter(where competitive) competitive_awards,
        count(*) filter(where competitive and try_cast(number_of_offers_received as int)>0) competitive_with_offers,
        count(*) filter(where competitive and try_cast(number_of_offers_received as int)=1) single_offer_awards
        from ay group by 1,2 having count(*)>=10 order by awards desc,fy,naics_code""")
    parent_history = rows("""select recipient_uei,any_value(recipient_name) name,
        count(distinct reported_parent) parent_ids, count(*) observations
        from t group by 1 having count(distinct reported_parent)>1 order by parent_ids desc,name""")
    # Two coherent, deterministic parent conventions are sensitivity scenarios,
    # not probabilistic ownership estimates or inferred historical transitions.
    c.execute("""create table latest_parent as select recipient_uei,reported_parent from t
        qualify row_number() over(partition by recipient_uei order by action desc,last_modified_date desc,
        contract_transaction_unique_key desc)=1""")
    grouping = []
    for label, entity, join in [
        ("recipient_uei", "t.recipient_uei", ""),
        ("parent_reported_on_action", "reported_parent", ""),
        ("latest_observed_parent", "p.reported_parent", "join latest_parent p using(recipient_uei)"),
    ]:
        rr = rows(f"""with s as (select fy,{entity} entity,greatest(sum(obligation),0) e from t {join} group by 1,2),
            shares as(select *, e/sum(e) over(partition by fy) share from s)
            select fy,count(*) groups,sum(pow(share,2))*10000 hhi,max(share) top_share
            from shares group by fy order by fy""")
        grouping.append({"scenario": label, "annual": rr})

    # Resample whole awards, preserving within-award action dependence. The interval
    # describes sensitivity to the portfolio mix, not uncertainty in a census total.
    bootstrap = []
    rng = np.random.default_rng(20261025)
    for year in [2022, 2023, 2024]:
        x = np.array(c.execute("""select sum(exposure),sum(case when month(action)=9 then exposure else 0 end)
            from t where fy=? group by contract_award_unique_key order by contract_award_unique_key""", [year]).fetchall(), dtype=float)
        draws = []
        for _ in range(1000):
            sample = x[rng.integers(0, len(x), len(x))].sum(axis=0)
            draws.append(sample[1] / sample[0] if sample[0] else 0)
        bootstrap.append({"fy": year, "awards": len(x), "replicates": 1000,
            "p025": float(np.quantile(draws, .025)), "p975": float(np.quantile(draws, .975))})

    # Select source examples by explicit SQL criteria rather than a risk label.
    largest = rows("""select contract_award_unique_key award_id,any_value(award_id_piid) piid,
        any_value(recipient_name) recipient,any_value(usaspending_permalink) url,
        sum(obligation) net,sum(exposure) positive,count(*) actions,
        min(action) first_observed,max(action) last_observed
        from t group by 1 order by positive desc,award_id limit 1""")[0]
    negative = rows("""select contract_transaction_unique_key transaction_id,contract_award_unique_key award_id,
        award_id_piid piid,recipient_name recipient,usaspending_permalink url,action,fy,obligation,
        modification_number modification from t where obligation<0 order by obligation,transaction_id limit 1""")[0]
    sept = rows("""select contract_transaction_unique_key transaction_id,contract_award_unique_key award_id,
        award_id_piid piid,recipient_name recipient,usaspending_permalink url,action,fy,obligation,
        naics_code,extent_competed,number_of_offers_received
        from t where month(action)=9 and obligation>0 order by obligation desc,transaction_id limit 1""")[0]
    cases = [
        {"id": "portfolio-concentration", "title": "A large commitment stream needs contract context",
         "question": "How much of the observed portfolio runs through one award?",
         "selection": "Award with largest sum of positive action obligations in the cohort.",
         "record": largest, "denominator": overview["positive"],
         "metric_value": f"{float(largest['positive']/overview['positive']):.2%}",
         "metric_label": "of cohort positive commitments in this award",
         "denominator_text": f"${overview['positive']:,.2f} in positive action obligations across all 4,683 cohort actions; numerator ${largest['positive']:,.2f} across {largest['actions']} actions in this award.",
         "formula": "sum(greatest(federal_action_obligation,0)) by award / cohort positive obligations",
         "sql": "with a as (select award_id,sum(positive_obligation) positive from fact_transactions group by 1) select *,positive/sum(positive) over() cohort_share from a order by positive desc limit 1;",
         "interpretation": "This is an observed funding stream, not the award ceiling or a cash payment. An existing contract can receive multiple funding actions.",
         "alternative_explanations": ["Agency mission and specialized services", "Multi-year funding and option exercises", "Use of an established contract vehicle"],
         "uncertainty": "Exact UEIs identify recipients. Parent grouping is a separate sensitivity choice; a large award remains the same award under either convention."},
        {"id": "deobligation", "title": "A negative action is part of the accounting",
         "question": "What changes when reductions in commitments are retained?",
         "selection": "Most negative individual action obligation in the cohort.",
         "record": negative, "denominator": overview["transactions"],
         "metric_value": f"-${abs(negative['obligation']):,.2f}",
         "metric_label": "signed obligation on the selected modification",
         "formula": "min(federal_action_obligation) across all cohort actions; accounting identity: net = positive + negative obligations",
         "sql": "select transaction_id, obligation from fact_transactions where obligation<0 order by obligation limit 1;",
         "interpretation": "A deobligation reduces a prior commitment. It must remain in net totals and timelines. Its size alone cannot establish whether the underlying activity was appropriate.",
         "alternative_explanations": ["Contract closeout and unused balances", "A scope or funding correction", "Reversal or administrative adjustment"],
         "uncertainty": "The observation window excludes earlier actions. Cumulative amounts begin at the window boundary, not contract inception."},
        {"id": "year-end", "title": "September commitments invite a timing question",
         "question": "Is the year-end pattern broad or driven by a small number of awards?",
         "selection": "Largest positive September action in the cohort.",
         "record": sept, "denominator": next(a['positive'] for a in annual if a['fy']==sept['fy']),
         "metric_value": f"{next(a['september_positive_share'] for a in annual if a['fy']==sept['fy']):.1%}",
         "metric_label": f"September share of FY{sept['fy']} positive commitments",
         "denominator_text": f"All positive action obligations in FY{sept['fy']}: ${next(a['positive'] for a in annual if a['fy']==sept['fy']):,.2f}. The linked action is the largest positive September action, shown as context rather than the full numerator.",
         "formula": "September positive obligations / all positive obligations within each fiscal year",
         "sql": "select fiscal_year, sum(case when month(action_date)=9 then greatest(obligation,0) else 0 end)/sum(greatest(obligation,0)) share from fact_transactions group by 1;",
         "interpretation": "Compare the annual distribution and award-mix resampling before generalizing. Timing can reflect budget availability and scheduled procurement cycles.",
         "alternative_explanations": ["Fiscal-year funding availability", "Scheduled renewal or option dates", "A few high-value awards dominating a small cohort"],
         "uncertainty": "Resampling whole awards measures composition stability, not a confidence interval for the observed census or evidence of causality."},
    ]
    result = {"scope": "NRC awarding agency; A/B/C/D contracts; FY2022–FY2024",
        "overview": overview, "annual": annual, "positive_transaction_distribution": tails,
        "naics_composition": composition, "award_year_competition_peers": peers,
        "recipients_with_multiple_reported_parents": parent_history,
        "entity_grouping_sensitivity": grouping, "september_award_mix_bootstrap": bootstrap,
        "bootstrap_note": "Seed 20261025; 1000 resamples of whole awards per FY. Composition sensitivity, not population confidence or causal inference.",
        "sql_source": "civicledger/reports.py", "case_count": len(cases),
        "source_snapshot": json.loads((root / "data/processed/manifest.json").read_text())["snapshot_id"],
        "source_csv_sha256": json.loads((root / "data/processed/manifest.json").read_text())["public_csv"]["sha256"]}
    def default(x):
        if hasattr(x, "isoformat"):
            return x.isoformat()
        return float(x)
    (out / "analysis.json").write_text(json.dumps(result, indent=2, default=default) + "\n")
    (out / "cases.json").write_text(json.dumps(cases, indent=2, default=default) + "\n")
    write_markdown(result, cases, root)
    return result


def write_markdown(r: dict, cases: list, root: Path):
    o, q = r["overview"], r["positive_transaction_distribution"]
    money = lambda v: f"${v:,.2f}"
    pct = lambda v: f"{float(v):.1%}"
    lines = ["# NRC procurement: evidence and sensitivity", "",
        f"This is the full downloaded cohort of {o['transactions']:,} reported contract actions across {o['awards']:,} awards and {o['recipients']:,} recipient UEIs, FY2022–FY2024. It is a current-source retrospective snapshot, not a reconstruction of what the database showed in each historical year.", "",
        "## Accounting and a heavy-tailed portfolio", "",
        f"Net obligations are {money(o['net'])}: {money(o['positive'])} of positive commitments plus {money(o['negative'])} of deobligations. There are {o['negative_actions']:,} negative, {o['zero_actions']:,} zero and {o['positive_actions']:,} positive actions. Removing negatives would overstate net spending. Obligations are commitments, not outlays, realized costs or ceilings.", "",
        f"Among positive actions, median obligation is {money(q['median'])}, the 90th percentile is {money(q['p90'])}, the 99th percentile is {money(q['p99'])}, and the maximum is {money(q['maximum'])}. The top ceil(1% × {q['n_positive']}) positive actions account for {pct(q['top_one_percent_share'])} of positive commitments. This tail makes averages and raw-total rankings poor peer comparisons.", "",
        "## Annual composition", "", "| FY | Net obligations | Positive commitments | Awards | September share of positive commitments | Recipient HHI |", "|---|---:|---:|---:|---:|---:|"]
    for x in r["annual"]:
        lines.append(f"| {x['fy']} | {money(x['net'])} | {money(x['positive'])} | {x['awards']} | {pct(x['september_positive_share'])} | {x['hhi']:.1f} |")
    lines += ["", "HHI is 10,000 × sum(positive recipient-year net balance share²) within fiscal year. Negative recipient-year net balances receive zero HHI weight; all signed actions remain in net totals. The same signed-net totals reconcile with the official transaction-level aggregate. See `data/processed/validation.json` and the retrieval manifest for filters and source receipt hashes.", "", "## What is being bought", "", "| NAICS | Description | Positive-obligation share | Awards |", "|---|---|---:|---:|"]
    for x in r["naics_composition"]:
        lines.append(f"| {x['naics_code']} | {x['description']} | {pct(x['share'])} | {x['awards']} |")
    lines += ["", "These are industry classifications, not interchangeable purchases. Even within an industry, contract size, complexity, vehicle and legally permitted procedures can differ.", "", "## Competition and missingness", "",
        f"{o['missing_competition']} of {o['transactions']} action records have no classified competition status; {o['missing_offers']} lack a usable offer count. Unknown values do not become noncompetitive or single-offer observations. {o['missing_parent']} records lack a parent UEI. Every action has a recipient UEI.", "",
        "Peer comparisons use the latest observed action per award and fiscal year, with deterministic action-date/revision/key ordering. This prevents a frequently modified award from counting as many separate competitions. It remains a reporting proxy because a modification is not necessarily a new competition. A single-offer denominator includes only competitive award-year observations with a positive reported offer count. See `analysis.json` for every numerator and denominator.", "", "## Entity grouping changes the question", "",
        f"{len(r['recipients_with_multiple_reported_parents'])} recipient UEIs have more than one reported parent identifier across the window. This can reflect reorganization, correction, reporting conventions or ownership changes; the snapshot alone cannot distinguish them. We retain the action-level attribute history instead of silently backdating the latest parent.", "", "| Grouping convention | FY2022 HHI | FY2023 HHI | FY2024 HHI |", "|---|---:|---:|---:|"]
    for x in r["entity_grouping_sensitivity"]:
        lines.append(f"| {x['scenario']} | " + " | ".join(f"{v['hhi']:.1f}" for v in x["annual"]) + " |")
    lines += ["", "These scenarios are explicit alternative definitions, not posterior uncertainty intervals. UEI resolves legal-recipient identity; parent aggregation asks a broader question. Fuzzy name matching must not overwrite conflicting UEIs.", "", "## Statistical stability of the year-end pattern", "",
        "This cohort is a census of the selected records, so a sampling confidence interval for its exact total is inappropriate. We instead resample entire awards with replacement within each FY, preserving their action histories. The 2.5th–97.5th percentile range across 1,000 replicates describes how September's positive-obligation share responds to portfolio composition. Seed: 20261025.", "", "| FY | Award clusters | Award-mix resampling range |", "|---|---:|---:|"]
    for x in r["september_award_mix_bootstrap"]:
        lines.append(f"| {x['fy']} | {x['awards']} | {pct(x['p025'])}–{pct(x['p975'])} |")
    lines += ["", "This does not identify a causal year-end effect. It does not model reporting error or unobserved contracts. Look at individual timelines and peers before making a decision.", "", "## Reproduction and boundaries", "",
        "Run `python -m civicledger.reports` after acquisition/warehouse build. Every value above is emitted to `data/reports/analysis.json` from SQL in `civicledger/reports.py`. Data are limited to the awarding agency, contract types and action-date range in the manifest. Grants, subawards, IDVs, spending by other agencies and actions outside the window are excluded. Award counts are window activity counts; entry and exit are observed within-window presence, not business formation or market withdrawal.", "",
        "The [three analytical case studies](CASE_STUDIES.md) link directly to the original award records. The separate [linkage study](LINKAGE.md) evaluates identity masking and review allocation; it is not a misconduct detector."]
    (root / "docs/EDA.md").write_text("\n".join(lines) + "\n")
    lines = ["# Three source-traceable analytical cases", "", "These are selected observations and review questions, not findings of wrongdoing. The selection rule is disclosed for each case. Source data are in the retrieval manifest's snapshot; the official award page may show later revisions or lifetime totals."]
    for case in cases:
        record = case["record"]
        lines += ["", "## " + case["title"], "", case["question"], "", "Selection: " + case["selection"], "", f"Source: [{record['piid']}]({record['url']}) · {record['recipient']}.", "", "```json", json.dumps(record, indent=2, default=str), "```", "", "Metric: " + case["metric_value"] + " · " + case["metric_label"], "", "Denominator: " + case.get("denominator_text", str(case["denominator"])), "", "Formula: " + case["formula"], "", "```sql", case["sql"], "```", "", case["interpretation"], "", "Plausible explanations to check: " + "; ".join(case["alternative_explanations"]) + ".", "", "Sensitivity and limits: " + case["uncertainty"]]
    lines += ["", "The explorer provides each award's in-window action timeline, signed obligation amounts, recipient identifiers and source link. Exported dossiers include the current filters and evidence. A review conclusion should specify what additional records would resolve the question and whether entity grouping would change it."]
    (root / "docs/CASE_STUDIES.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    result = build()
    print(json.dumps({"reports": "data/reports", "transactions": result["overview"]["transactions"], "cases": result["case_count"]}))
