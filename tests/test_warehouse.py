"""Contract and provenance checks, including a small clearly synthetic accounting fixture."""
import csv, hashlib, json
from decimal import Decimal
from pathlib import Path
import duckdb
import pytest
from civicledger.ingest import CONTACT_RE, PUBLIC_COLUMNS, sanitize_rows
from civicledger.warehouse import ROOT

@pytest.fixture(scope='module')
def rows():
    with (ROOT/'data/processed/transactions.csv').open(newline='') as f:return list(csv.DictReader(f))

def test_snapshot_hash_and_scope(rows):
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text())
    assert hashlib.sha256((ROOT/'data/processed/transactions.csv').read_bytes()).hexdigest()==manifest['public_csv']['sha256']
    assert len(rows)==manifest['expected_transaction_count']
    assert len({r['contract_transaction_unique_key'] for r in rows})==len(rows)
    assert all('2021-10-01'<=r['action_date']<='2024-09-30' for r in rows)
    assert all(r['awarding_agency_name']=='Nuclear Regulatory Commission' for r in rows)
    assert all(r['award_type_code'] in ('A','B','C','D') for r in rows)

def test_public_projection_minimizes_contact_data(rows):
    assert set(rows[0]).issubset(PUBLIC_COLUMNS)
    assert not any('street' in k or 'phone' in k or 'officer' in k or 'email' in k for k in rows[0])
    assert not any(CONTACT_RE.search(r.get('transaction_description','')) for r in rows)
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text())
    assert manifest['public_transformations']['contact_bearing_descriptions_omitted']==sum(r.get('transaction_description')=='[Contact-bearing description omitted; see official source.]' for r in rows)

def test_redaction_omits_whole_description():
    samples=[{'transaction_description':'Call PERSON NAME at 202-555-0101 for award details'},
             {'transaction_description':'Contact PERSON NAME at test@example.com'},
             {'transaction_description':'Routine option extension, no contact details'}]
    assert sanitize_rows(samples)==2
    assert 'PERSON NAME' not in samples[0]['transaction_description']
    assert 'PERSON NAME' not in samples[1]['transaction_description']
    assert samples[2]['transaction_description'].startswith('Routine')

def test_original_raw_provenance_when_available():
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text())
    raw=ROOT/'data/raw'/manifest['snapshot_id']
    if not (raw/'source.zip').exists():pytest.skip('Original full-field archives intentionally not distributed publicly')
    archive=next(a for a in manifest['artifacts'] if a['path']=='source.zip')
    assert hashlib.sha256((raw/'source.zip').read_bytes()).hexdigest()==archive['sha256']
    source=next(a for a in manifest['archive_entries'] if Path(a['name']).name==manifest['source_csv'])
    assert hashlib.sha256((raw/manifest['source_csv']).read_bytes()).hexdigest()==source['sha256']

def test_signed_obligations_reconcile_exactly(rows):
    official=json.loads((ROOT/'data/processed/official_annual.json').read_text())
    for year in official['results']:
        fy=year['time_period']['fiscal_year']
        actual=sum(Decimal(r['federal_action_obligation']) for r in rows if r['action_date_fiscal_year']==fy)
        assert actual==Decimal(str(year['aggregated_amount']))
    assert any(Decimal(r['federal_action_obligation'])<0 for r in rows)

def test_accounting_edge_cases_are_preserved(tmp_path,rows):
    # Synthetic actions derived from one schema row. NOT observational data or a fraud example.
    fixture=[]
    for n,(date,amount,recipient,competition,offers) in enumerate([
        ('2021-10-01','100.00','UEI_A','A','1'),
        ('2022-01-01','-40.00','UEI_A','A','1'),
        ('2022-02-01','0.00','UEI_A','',''),
        ('2022-09-30','40.00','UEI_B','C',''),
    ]):
        r=dict(rows[0]);r.update({'contract_transaction_unique_key':f'TEST{n}','contract_award_unique_key':f'TEST_AWARD_{recipient}',
          'action_date':date,'action_date_fiscal_year':'2022','federal_action_obligation':amount,
          'recipient_uei':recipient,'extent_competed_code':competition,'number_of_offers_received':offers,
          'recipient_parent_uei':recipient})
        fixture.append(r)
    path=tmp_path/'synthetic.csv'
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fixture[0]);w.writeheader();w.writerows(fixture)
    con=duckdb.connect()
    con.execute('CREATE TABLE raw_transactions AS SELECT * FROM read_csv(?,all_varchar=true,nullstr=\'\')',[str(path)])
    con.execute((ROOT/'sql/01_warehouse.sql').read_text())
    assert con.execute('SELECT sum(obligation) FROM fact_transactions').fetchone()[0]==Decimal('100.00')
    assert con.execute('SELECT sum(net_obligations) FROM mart_awards').fetchone()[0]==Decimal('100.00')
    # Positive recipient net weights 60:40 => HHI 5,200. Gross-action weights 100:40 would be a DIFFERENT metric.
    assert con.execute('SELECT hhi FROM annual_concentration').fetchone()[0]==pytest.approx(5200)
    assert con.execute('SELECT missing_competition_transactions FROM annual_summary').fetchone()[0]==1
    assert con.execute('SELECT missing_offers_transactions FROM annual_summary').fetchone()[0]==2
    assert con.execute("SELECT cumulative_in_cohort_obligation FROM award_timeline WHERE transaction_id='TEST2'").fetchone()[0]==Decimal('60.00')
    assert all(n==0 for _,n in con.execute((ROOT/'sql/02_validation.sql').read_text()).fetchall())
    con.close()
