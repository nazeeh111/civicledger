"""Immutable, replayable USAspending prime-contract transaction acquisition.

Raw bulk files can include unneeded address/officer fields. They remain local.
The public replay snapshot is an explicit column-minimized projection, not a new
source: its original row identifiers and digest point back to the raw manifest.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, re, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://api.usaspending.gov'
FILTERS = {
    'agencies': [{'type': 'awarding', 'tier': 'toptier', 'name': 'Nuclear Regulatory Commission'}],
    'award_type_codes': ['A', 'B', 'C', 'D'],
    'time_period': [{'start_date': '2021-10-01', 'end_date': '2024-09-30'}],
}
REQUEST = {'filters': FILTERS, 'file_format': 'csv', 'limit': 500000}
PUBLIC_COLUMNS = [
    'contract_transaction_unique_key', 'contract_award_unique_key', 'award_id_piid',
    'modification_number', 'transaction_number', 'parent_award_agency_id', 'parent_award_id_piid',
    'federal_action_obligation', 'total_dollars_obligated', 'current_total_value_of_award',
    'potential_total_value_of_award', 'action_date', 'action_date_fiscal_year',
    'period_of_performance_start_date', 'period_of_performance_current_end_date',
    'awarding_agency_code', 'awarding_agency_name', 'awarding_sub_agency_code', 'awarding_sub_agency_name',
    'awarding_office_code', 'awarding_office_name', 'funding_agency_code', 'funding_agency_name',
    'recipient_uei', 'recipient_duns', 'recipient_name', 'recipient_doing_business_as_name',
    'recipient_parent_uei', 'recipient_parent_duns', 'recipient_parent_name',
    'recipient_city_name', 'recipient_state_code', 'recipient_country_code',
    'naics_code', 'naics_description', 'product_or_service_code', 'product_or_service_code_description',
    'award_type_code', 'award_type', 'type_of_contract_pricing_code', 'type_of_contract_pricing',
    'extent_competed_code', 'extent_competed', 'number_of_offers_received',
    'solicitation_procedures_code', 'solicitation_procedures', 'type_of_set_aside_code', 'type_of_set_aside',
    'award_description', 'transaction_description', 'last_modified_date', 'initial_report_date', 'usaspending_permalink',
]

CONTACT_RE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?1[-. ()]*)?\(?\d{3}\)?[-. ]*\d{3}[-. ]*\d{4}')
REDACTION = '[Contact-bearing description omitted; see official source.]'
def sanitize_rows(rows):
    redacted = 0
    for row in rows:
        for field in ('transaction_description','award_description'):
            if CONTACT_RE.search(row.get(field,'') or ''):
                row[field]=REDACTION; redacted+=1
    return redacted

def now(): return datetime.now(timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()
def write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
def call(method, endpoint, body=None):
    url = endpoint if endpoint.startswith('https://') else BASE + endpoint
    for attempt in range(5):
        try:
            r = requests.request(method, url, json=body, timeout=120, headers={'User-Agent': 'CivicLedger-research/1.0'})
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 4: raise
            time.sleep(2 ** attempt)

def acquire(resume=None):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw = ROOT / 'data/raw' / stamp
    raw.mkdir(parents=True, exist_ok=False)
    manifest = {'snapshot_id': stamp, 'started_at': now(), 'filters': FILTERS, 'request': REQUEST,
                'source': BASE, 'artifacts': [], 'privacy': 'Raw archive is local-only. Published CSV is column-minimized.'}
    def receipt(name, method, endpoint, body=None):
        response = call(method, endpoint, body)
        payload = response.content
        (raw / name).write_bytes(payload)
        manifest['artifacts'].append({'path':name,'sha256':digest(payload),'bytes':len(payload),
              'url':response.url,'method':method,'request':body,'retrieved_at':now(),
              'response_headers':{k:v for k,v in response.headers.items() if k.lower() in ('date','last-modified','etag','content-type')}})
        return response.json()
    count = receipt('transaction_count.json','POST','/api/v2/search/spending_by_transaction_count/', {'filters':FILTERS})
    official = receipt('official_annual.json','POST','/api/v2/search/spending_over_time/',
                       {'group':'fiscal_year','spending_level':'transactions','filters':FILTERS})
    if resume:
        job = json.loads(Path(resume).read_text())
        write_json(raw/'download_request_receipt.json',job)
        manifest['resumed_job'] = True
    else:
        job = receipt('download_request_receipt.json','POST','/api/v2/download/transactions/',REQUEST)
    deadline = time.monotonic() + 1800
    poll = 0
    while True:
        status = receipt(f'status_{poll:03d}.json','GET',job['status_url'])
        print(json.dumps({'download_status':status.get('status'),'seconds_elapsed':status.get('seconds_elapsed')}),flush=True)
        if status.get('status') == 'finished': break
        if status.get('status') in ('failed','error'): raise RuntimeError(status)
        if time.monotonic() > deadline: raise TimeoutError('USAspending bulk job not ready within 30 minutes; resume existing receipt.')
        poll += 1
        time.sleep(15)
    response = call('GET',job['file_url'])
    archive = response.content
    (raw/'source.zip').write_bytes(archive)
    manifest['artifacts'].append({'path':'source.zip','sha256':digest(archive),'bytes':len(archive),
                                 'url':response.url,'retrieved_at':now()})
    z = zipfile.ZipFile(io.BytesIO(archive))
    entries = []
    transaction_files = []
    for name in z.namelist():
        b=z.read(name)
        entries.append({'name':name,'bytes':len(b),'sha256':digest(b)})
        if name.lower().endswith('.csv') and ('contract' in name.lower()) and ('sub' not in name.lower()):
            path=raw/Path(name).name
            path.write_bytes(b)
            transaction_files.append(path)
    if len(transaction_files)!=1:
        raise RuntimeError(f'Expected one prime-contract CSV; got {transaction_files}; zip entries {entries}')
    source_csv=transaction_files[0]
    with source_csv.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        fields=[c for c in PUBLIC_COLUMNS if c in reader.fieldnames]
        rows=list(reader)
    expected=count['results']['contracts']
    if len(rows)!=expected:
        raise ValueError(f'Incomplete or changing snapshot: CSV {len(rows)} versus count {expected}')
    redactions = sanitize_rows(rows)
    public = ROOT/'data/processed/transactions.csv'
    public.parent.mkdir(parents=True,exist_ok=True)
    with public.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    manifest.update({'completed_at':now(),'source_csv':str(source_csv.relative_to(raw)),
      'archive_entries':entries,'row_count':len(rows),'expected_transaction_count':expected,
      'source_columns':reader.fieldnames,'public_columns':fields,
      'public_transformations':{'contact_bearing_descriptions_omitted':redactions,'rule':'Whole description omitted when an email address or North American telephone pattern is detected; raw original unchanged.'},
      'unavailable_requested_columns':[c for c in PUBLIC_COLUMNS if c not in fields],
      'public_csv':{'path':'data/processed/transactions.csv','sha256':digest(public.read_bytes()),'bytes':public.stat().st_size},
      'official_annual':official})
    write_json(raw/'manifest.json',manifest)
    # Public manifest has filenames/hashes/retrieval provenance, no excluded data values.
    write_json(ROOT/'data/processed/manifest.json',manifest)
    write_json(ROOT/'data/processed/official_annual.json',official)
    print(json.dumps({'snapshot':stamp,'rows':len(rows),'public_columns':len(fields),'public_csv':str(public)}),flush=True)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--resume',help='Path to existing download-request receipt JSON')
    acquire(p.parse_args().resume)
