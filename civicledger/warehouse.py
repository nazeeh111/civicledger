"""Build the local warehouse and reproducible public explorer projection."""
from __future__ import annotations
import argparse, csv, hashlib, json, statistics, time
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data/warehouse.duckdb'

def default(v):
    if isinstance(v,Decimal):return float(v)
    if isinstance(v,(date,datetime)):return v.isoformat()
    raise TypeError(type(v).__name__)
def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,default=default,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def records(con,sql):
    cur=con.execute(sql); names=[a[0] for a in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]

def build():
    DB.parent.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(DB))
    # Every column is loaded as text first. Casts and null handling are explicit in versioned SQL.
    csvpath=str(ROOT/'data/processed/transactions.csv').replace("'","''")
    con.execute(f"CREATE OR REPLACE TABLE raw_transactions AS SELECT * FROM read_csv('{csvpath}',all_varchar=true,header=true,nullstr='')")
    con.execute((ROOT/'sql/01_warehouse.sql').read_text())
    tests=records(con,(ROOT/'sql/02_validation.sql').read_text())
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text())
    official=json.loads((ROOT/'data/processed/official_annual.json').read_text())
    annual=records(con,'SELECT * FROM annual_summary ORDER BY fiscal_year')
    reconciliation=[]
    for row in official['results']:
        fy=int(row['time_period']['fiscal_year']); amount=Decimal(str(row['aggregated_amount']))
        actual=next(a['net_obligations'] for a in annual if a['fiscal_year']==fy)
        reconciliation.append({'fiscal_year':fy,'warehouse_obligations':actual,'official_transaction_obligations':amount,
                               'difference':actual-amount,'pass':abs(actual-amount)<=Decimal('0.01')})
    tests.append({'test':'source_transaction_count','violations':abs(con.execute('SELECT count(*) FROM fact_transactions').fetchone()[0]-manifest['expected_transaction_count'])})
    tests.append({'test':'official_annual_reconciliation','violations':sum(not r['pass'] for r in reconciliation)})
    validation={'duckdb_version':duckdb.__version__,'snapshot_id':manifest['snapshot_id'],
                'tests':tests,'reconciliation':reconciliation,'all_passed':all(t['violations']==0 for t in tests)}
    save_json(ROOT/'data/processed/validation.json',validation)
    if not validation['all_passed']: raise ValueError(validation)
    # Repeated warm-cache, single-process timings. Not a scale or other-engine benchmark.
    queries={
      'annual_concentration':'SELECT * FROM annual_concentration',
      'award_timelines':'SELECT award_id,max(cumulative_in_cohort_obligation) FROM award_timeline GROUP BY award_id',
      'peer_competition':'SELECT * FROM peer_competition WHERE adequate_peer_size ORDER BY single_offer_rate DESC',
      'history_join':'SELECT h.recipient_name,sum(f.obligation) FROM fact_transactions f JOIN dim_recipient_history h USING(recipient_history_id) GROUP BY h.recipient_name',
    }
    perf=[]
    for name,query in queries.items():
        con.execute(query).fetchall()
        timings=[]
        for _ in range(7):
            start=time.perf_counter(); result=con.execute(query).fetchall();timings.append((time.perf_counter()-start)*1000)
        plan=con.execute('EXPLAIN ANALYZE '+query).fetchone()[1]
        (ROOT/'data/processed'/f'profile_{name}.txt').write_text(plan)
        perf.append({'query':name,'sql':query,'returned_rows':len(result),'runs':7,
                     'median_ms':statistics.median(timings),'min_ms':min(timings),'max_ms':max(timings)})
    save_json(ROOT/'data/processed/performance.json',{'engine':'DuckDB '+duckdb.__version__,'rows':manifest['row_count'],
      'conditions':'Local laptop, seven warm-cache runs, one connection, full result materialization included; not a large-scale benchmark.',
      'queries':perf})
    export(con,manifest,annual,validation)
    con.close()
    print(json.dumps({'database':str(DB),'rows':manifest['row_count'],'sql_checks':len(tests),'all_passed':True}))

def export(con,manifest,annual,validation):
    tx=records(con,"""SELECT transaction_id,award_id,piid,modification_number,recipient_id,recipient_name,
      parent_id,parent_name,action_date,fiscal_year,obligation,positive_obligation,competition,competition_code,
      offers_received,naics,naics_description,psc,psc_description,description,source_url,
      source_last_modified,agency_name,subagency_name,recipient_history_id,
      cumulative_in_cohort_obligation FROM award_timeline ORDER BY action_date,transaction_id""")
    awards=records(con,'SELECT * FROM mart_awards ORDER BY net_obligations DESC')
    recipients=records(con,"""SELECT recipient_id,arg_max(recipient_name,action_date) AS recipient_name,
      sum(obligation) AS net_obligations,sum(positive_obligation) AS positive_obligations,
      count(*) AS transactions,count(DISTINCT award_id) AS awards,count(DISTINCT recipient_name) AS observed_names,
      count(DISTINCT parent_id) AS observed_parents,
      arg_max(parent_name,action_date) AS latest_observed_parent
      FROM fact_transactions GROUP BY recipient_id ORDER BY net_obligations DESC""")
    peers=records(con,'SELECT * FROM peer_competition ORDER BY fiscal_year,positive_obligations DESC')
    histories=records(con,'SELECT * FROM dim_recipient_history ORDER BY recipient_id,first_observed')
    monthly=records(con,'SELECT * FROM monthly_patterns ORDER BY fiscal_year,calendar_month')
    missing=records(con,"""SELECT count(*) AS denominator,
      count(*) FILTER(WHERE recipient_duns IS NULL) AS duns_missing,
      count(*) FILTER(WHERE recipient_id IS NULL) AS uei_missing,
      count(*) FILTER(WHERE offers_received IS NULL) AS offers_missing,
      count(*) FILTER(WHERE competition_code IS NULL) AS competition_missing,
      count(*) FILTER(WHERE naics IS NULL) AS naics_missing,
      count(*) FILTER(WHERE parent_id IS NULL) AS parent_missing,
      count(*) FILTER(WHERE recipient_city IS NULL) AS city_missing,
      count(*) FILTER(WHERE obligation<0) AS negative_actions,
      count(*) FILTER(WHERE obligation=0) AS zero_actions
      FROM fact_transactions""")[0]
    heavy=records(con,"""WITH a AS (
      SELECT *,row_number() OVER(ORDER BY greatest(net_obligations,0) DESC,award_id) AS rnk,
      count(*) OVER() AS n,sum(greatest(net_obligations,0)) OVER() AS total_weight FROM mart_awards)
      SELECT count(*) AS awards,quantile_cont(net_obligations,0.5) AS median_award_net,
      quantile_cont(net_obligations,0.9) AS p90_award_net,quantile_cont(net_obligations,0.99) AS p99_award_net,
      max(net_obligations) AS maximum_award_net,
      sum(greatest(net_obligations,0)) FILTER(WHERE rnk<=ceil(n*0.01))/max(total_weight) AS top1pct_award_share,
      sum(greatest(net_obligations,0)) FILTER(WHERE rnk<=ceil(n*0.10))/max(total_weight) AS top10pct_award_share
      FROM a""")[0]
    parent_changes=records(con,"""SELECT recipient_id,arg_max(recipient_name,action_date) AS recipient_name,
      count(DISTINCT parent_id) AS observed_parent_ids,sum(obligation) AS net_obligations,
      list(DISTINCT parent_name) AS observed_parent_names,
      list(DISTINCT source_url) AS source_urls
      FROM fact_transactions GROUP BY recipient_id HAVING count(DISTINCT parent_id)>1 ORDER BY net_obligations DESC""")
    entry_exit=records(con,"""SELECT fiscal_year,count(*) FILTER(WHERE first_year_observed) AS first_observed_recipients,
      count(*) FILTER(WHERE last_year_observed) AS last_observed_recipients,
      count(*) FILTER(WHERE first_year_observed AND fiscal_year>2022) AS entered_after_left_boundary,
      count(*) FILTER(WHERE last_year_observed AND fiscal_year<2024) AS absent_after_within_window
      FROM recipient_entry_exit GROUP BY fiscal_year ORDER BY fiscal_year""")
    metrics={
      'net_obligations':{'label':'Net obligations','formula':'SUM(federal_action_obligation), preserving negative actions','sql':'SELECT fiscal_year,SUM(obligation) FROM fact_transactions GROUP BY fiscal_year','denominator':'All in-scope prime contract transaction actions','interpretation':'A promise to pay, not cash disbursed; reversals reduce this total.','benign_explanation':'Routine option exercise, incremental funding and deobligation all change totals.','source_columns':['federal_action_obligation','action_date'],'source_sql':'sql/01_warehouse.sql'},
      'hhi':{'label':'Supplier HHI','formula':'10,000 × SUM((max(recipient-year net obligation,0) / SUM(max(recipient-year net obligation,0)))²)','sql':'SELECT * FROM annual_concentration','denominator':'Sum of positive recipient-year net balances; negative recipient balances remain in net-obligation totals but have zero concentration weight.','interpretation':'0–10,000 scale; describes allocation within NRC, not the relevant economic market.','benign_explanation':'Specialized scientific and technical requirements may concentrate funding.','source_columns':['recipient_uei','federal_action_obligation'],'source_sql':'sql/01_warehouse.sql'},
      'top4_share':{'label':'Top-four share','formula':'Sum of the four largest positive recipient-year net shares','sql':'SELECT fiscal_year,top4_share FROM annual_concentration','denominator':'Positive recipient-year net balances','benign_explanation':'Large multiyear service awards and specialized expertise can explain concentrated allocations.','source_sql':'sql/01_warehouse.sql'},
      'competition_share':{'label':'Competed gross obligations','formula':"SUM(max(obligation,0)) FILTER(WHERE competition_code IN ('A','D','F')) / SUM(max(obligation,0))",'sql':'SELECT * FROM peer_competition','denominator':'Positive action obligations, including unknown competition in denominator','interpretation':'Recorded extent competed; modifications inherit competition context and do not represent new tenders.','benign_explanation':'Authorized sole-source or follow-on work may be recorded as not competed.','source_columns':['extent_competed_code','federal_action_obligation'],'source_sql':'sql/01_warehouse.sql'},
      'single_offer_rate':{'label':'Single-offer competed action rate','formula':'Competed actions with one reported offer / competed actions with known number of offers','sql':'SELECT * FROM peer_competition WHERE adequate_peer_size','denominator':'Competed action records with known offers, not distinct procurements','interpretation':'Modifications can repeat an award’s offer count. Bid-level participation and bidder identities are unavailable.','benign_explanation':'Specialist markets, incumbent expertise or a narrow scope can yield a single offer.','source_sql':'sql/01_warehouse.sql'},
      'september_share':{'label':'September share','formula':'September positive action obligations / annual positive action obligations','sql':'SELECT * FROM monthly_patterns','denominator':'All positive action obligations in fiscal year','benign_explanation':'Budget availability, annual funding cycles and option timing can explain September concentrations.','source_columns':['action_date','federal_action_obligation'],'source_sql':'sql/01_warehouse.sql'},
      'parent_hhi':{'label':'Reported parent HHI','formula':'HHI after assigning EACH action to its contemporaneously reported parent UEI; fall back to recipient UEI','sql':'SELECT * FROM parent_year','denominator':'Positive parent-year net balances','interpretation':'Reported parent mappings change and are not verified beneficial ownership. Values can move in either direction because parent reports change within recipient histories.','benign_explanation':'Ownership, reporting corrections or identifier changes may explain parent changes.','source_sql':'sql/01_warehouse.sql'},
      'transaction_count':{'label':'Transaction records','formula':'COUNT(*) at source contract_transaction_unique_key grain','sql':'SELECT COUNT(*) FROM fact_transactions','denominator':'All filtered action records','benign_explanation':'Many modifications can represent routine incremental funding, not unusual behavior.','source_sql':'sql/01_warehouse.sql'},
      'award_count':{'label':'Awards observed','formula':'COUNT(DISTINCT contract_award_unique_key)','sql':'SELECT COUNT(*) FROM mart_awards','denominator':'Awards with at least one action in the selected window','benign_explanation':'Cohort includes older awards modified during these years.','source_sql':'sql/01_warehouse.sql'},
    }
    meta={'title':'CIVICLEDGER','agency':'Nuclear Regulatory Commission','scope':'NRC-awarded prime contract transactions; all sectors; action dates 2021-10-01 through 2024-09-30',
      'fiscal_years':[2022,2023,2024],'retrieved_at':manifest['completed_at'],'snapshot_id':manifest['snapshot_id'],'public_csv_sha256':manifest['public_csv']['sha256'],
      'filters':manifest['filters'],'source_url':'https://api.usaspending.gov/','raw_manifest':'data/processed/manifest.json',
      'transaction_count':len(tx),'award_count':len(awards),'recipient_count':len(recipients),
      'caveats':['Obligations are commitments, not cash outlays; outlay fields are unavailable here.',
      'All three fiscal years are complete calendar windows as of this retrieval; the source can revise historical records.',
      'Award timelines and first/last observation are truncated to this cohort, not award or supplier lifetime.',
      'No misconduct labels or fraud-detection accuracy; patterns are contextual review candidates.',
      'Names and parent reports are observed attributes. A UEI identifies a legal entity, not necessarily an independent corporate group.',
      f"Raw full-field archives remain local. {manifest.get('public_transformations',{}).get('contact_bearing_descriptions_omitted',0)} contact-bearing descriptions are omitted from this public snapshot."],
      'unavailable':['Tender notice dates and tender duration','Bidder identities and bid prices','Adjudicated misconduct labels','Reliable ultimate beneficial ownership','Cash outlays at transaction grain'],
      'privacy_transformations':manifest.get('public_transformations',{}),
      'concentration_convention':'Positive recipient-year net obligation shares, HHI 0–10000; signed net flows always retained separately.'}
    payload={'meta':meta,'annual':annual,'transactions':tx,'awards':awards,'recipients':recipients,'peers':peers,
             'histories':histories,'monthly':monthly,'missingness':missing,'heavy_tails':heavy,
             'parent_changes':parent_changes,'entry_exit':entry_exit,'metrics':metrics,'validation':validation}
    save_json(ROOT/'app/dist/data.json',payload)
    save_json(ROOT/'data/processed/analytics.json',{k:v for k,v in payload.items() if k not in ('transactions','awards','histories')})
    for name in ('annual_summary','peer_competition','recipient_year','monthly_patterns','recipient_entry_exit','composition','mart_awards'):
        path=str(ROOT/'data/processed'/f'{name}.csv').replace("'","''")
        con.execute(f"COPY (SELECT * FROM {name}) TO '{path}' (HEADER,DELIMITER ',')")


def export_dbt():
    """Export the CURRENT built dbt tables and run results, called after dbt build."""
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text())
    result=json.loads((ROOT/'dbt/target/run_results.json').read_text())
    if not all(r['status'] in ('pass','success') for r in result['results']):
        raise RuntimeError('Refusing to export failed/incomplete dbt build')
    con=duckdb.connect(str(DB),read_only=True)
    for model in ('peer_award_year','revision_lag'):
        save_json(ROOT/'data/processed'/f'{model}.json',records(con,f'SELECT * FROM analytics.{model} ORDER BY 1,2'))
    summary={'snapshot_id':manifest['snapshot_id'],'public_csv_sha256':manifest['public_csv']['sha256'],
      'dbt_version':result['metadata']['dbt_version'],'generated_at':result['metadata']['generated_at'],
      'elapsed_time':result['elapsed_time'],
      'models_built':sum(r['unique_id'].startswith('model.') for r in result['results']),
      'data_tests':sum(r['unique_id'].startswith('test.') for r in result['results']),
      'all_passed':True,'results':[{'id':r['unique_id'],'status':r['status'],'execution_time':r['execution_time'],
      'failures':r['failures']} for r in result['results']]}
    save_json(ROOT/'data/processed/dbt_validation.json',summary)
    con.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.parse_args();build()
