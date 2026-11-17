"""Verify/recompute retained public evidence; optionally serve its pinned generation.
Requires Python3.12/3.13 and the declared duckdb==2.0.0 package. No network refresh.
"""
from pathlib import Path
import json,hashlib,sys,os,argparse,csv
from decimal import Decimal
import duckdb
P=Path(__file__).resolve().parent
for name,h in json.loads((P/'MANIFEST.json').read_text()).items():
 if hashlib.sha256((P/name).read_bytes()).hexdigest()!=h:raise ValueError('Changed bundle member: '+name)
W=P/'workspace';sys.path.insert(0,str(W));os.environ['PYTHONPATH']=str(W);os.environ['PYTHONDONTWRITEBYTECODE']='1'
from civicledger.workspace import resolve_generation,PublicHandler
from functools import partial
from http.server import ThreadingHTTPServer
saved=json.loads((P/'investigation.json').read_text());gid=saved['source']['generation_id'];g=resolve_generation(W,generation_id=gid);m=json.loads((g/'generation.json').read_text());con=duckdb.connect(str(g/'data/warehouse.duckdb'),read_only=True);award=saved['selection']['award_id'];query=(P/'query.sql').read_text();data=con.execute(query,[award]).fetchall();columns=[c[0]for c in con.description];rows=[dict(zip(columns,row))for row in data];assert sorted(r['transaction_id']for r in rows)==saved['record_ids']
net=sum((r['obligation']for r in rows),Decimal(0));assert net==Decimal(str(saved['metrics']['net']));raw=list(csv.DictReader((g/'data/processed/transactions.csv').open()));expected=sorted([r for r in raw if r['contract_award_unique_key']==award],key=lambda r:(r['action_date'],r['contract_transaction_unique_key']));running=Decimal(0)
for a,b in zip(rows,expected):
 running+=Decimal(b['federal_action_obligation']);assert a['transaction_id']==b['contract_transaction_unique_key']and a['obligation']==Decimal(b['federal_action_obligation'])and a['cumulative_in_cohort_obligation']==running
assert len(rows)==len(expected)==37;con.close();print(json.dumps({'all_manifest_paths_hash_exact':True,'native_pinned_generation_verified':gid,'all37OrderedActionsAndCumulativeValuesRecomputed':True,'net':str(net),'snapshot':m['snapshot_id'],'source':'Retained public minimized USAspending snapshot; commitments, not cash paid; no new retrieval or wrongdoing finding'},indent=2),flush=True)
p=argparse.ArgumentParser();p.add_argument('--serve',action='store_true');p.add_argument('--port',type=int,default=8185);a=p.parse_args()
if a.serve:
 server=ThreadingHTTPServer(('127.0.0.1',a.port),partial(PublicHandler,generation=g,expected=m['artifact_sha256']));print('Pinned explorer http://127.0.0.1:'+str(server.server_port),flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
