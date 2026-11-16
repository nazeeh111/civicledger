// Verify that the browser's aggregation preserves the published warehouse totals.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const dist=path.join(path.dirname(fileURLToPath(import.meta.url)),'dist');
for(const file of ['data.json','linkage.json','cases.json','reports.json'])assert.ok(fs.existsSync(path.join(dist,file)),`Required release artifact ${file} exists`);
const nodes=new Map();
const element=()=>({innerHTML:'',textContent:'',hidden:false,value:'',dataset:{},classList:{toggle(){}},addEventListener(){},setAttribute(){},removeAttribute(){},focus(){}});
const listeners={};
const document={querySelector:s=>{if(!nodes.has(s))nodes.set(s,element());return nodes.get(s);},querySelectorAll:()=>[],addEventListener(type,fn){listeners[type]=fn;}};
const sandbox={document,location:{href:'http://localhost/',hash:''},history:{replaceState(){}},window:{addEventListener(){}},console,URL,Intl,Blob,structuredClone,setTimeout,clearTimeout,fetch:async name=>{const file=path.join(dist,name);return {ok:fs.existsSync(file),status:fs.existsSync(file)?200:404,json:async()=>JSON.parse(fs.readFileSync(file,'utf8'))};}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(dist,'app.js'),'utf8'),sandbox);
await new Promise(resolve=>setTimeout(resolve,50));
const app=sandbox.window.CIVICLEDGER;assert.ok(app,'App initializes with the current source snapshot');
assert.ok(app.state.linkage,'Final linkage artifact initializes');
assert.equal(app.state.cases.length,3,'All three analytical cases initialize');
assert.ok(app.state.reports,'Final statistical report initializes');
assert.equal(app.state.linkage.source.snapshot_id,app.state.data.meta.snapshot_id,'Linkage uses current snapshot');
const csv=fs.readFileSync(path.resolve(dist,'../../data/processed/transactions.csv'));
assert.equal(app.state.linkage.source.public_csv_sha256,crypto.createHash('sha256').update(csv).digest('hex'),'Linkage source digest matches public CSV bytes');
for(const kind of ['real','synthetic'])assert.equal(app.state.linkage.benchmark[kind].splink_verification.status,'passed',`${kind} Splink runtime parity passed`);
assert.equal(app.state.reports.overview.transactions,app.state.data.transactions.length);
for(const c of app.state.cases)assert.ok(app.state.data.transactions.some(t=>t.award_id===c.record.award_id),'Every case cites a retained source award');
const synthetic=[['a','A',100],['a','A',-40],['a','A',0],['b','B',40]].map(([award_id,recipient_id,obligation],i)=>({award_id,recipient_id,recipient_name:recipient_id,obligation,action_date:'2022-09-01',competition:i<2?'A':null}));
const fixture=app.stats(synthetic);assert.equal(fixture.net,100);assert.equal(fixture.negative,-40);assert.equal(fixture.concentrationDenominator,100);assert.equal(fixture.hhi,5200);assert.equal(fixture.transactions,4);
const all=app.stats();
assert.equal(all.transactions,4683);assert.equal(all.awards,1588);assert.equal(all.recipients,537);
assert.ok(Math.abs(all.net-548751367.35)<0.001,'Net includes deobligations');
assert.ok(Math.abs(all.negative+17977335.52)<0.001,'All negative obligations retained');
assert.equal(all.concentrationDenominator,552755354.40,'Positive recipient-net denominator is exact to the cent');
assert.equal(all.competition.unknown,19,'Only missing competition stays unknown');
assert.equal(all.competition.competed,2932);assert.equal(all.competition.noncompetitive,1732);
for(const year of [2022,2023,2024]){
  const actual=app.stats(app.state.data.transactions.filter(r=>r.fiscal_year===year));
  const expected=app.state.data.annual.find(r=>r.fiscal_year===year);
  assert.ok(Math.abs(actual.net-expected.net_obligations)<0.001,`FY${year} net reconciles`);
  assert.ok(Math.abs(actual.hhi-expected.hhi)<1e-8,`FY${year} HHI uses the warehouse's positive-net denominator`);
  assert.ok(Math.abs(actual.top4-expected.top4_share)<1e-10,`FY${year} top four share reconciles`);
}
assert.equal(app.competitionClass('NOT COMPETED UNDER SAP'),'noncompetitive');
assert.equal(app.competitionClass('NOT AVAILABLE FOR COMPETITION'),'noncompetitive');
assert.equal(app.competitionClass('NON-COMPETITIVE DELIVERY ORDER'),'noncompetitive');
assert.equal(app.competitionClass('some unknown source value'),'unknown');
assert.equal(app.competitionClass(null),'unknown');
for(const award of app.selectedAwards().filter(a=>a.recipient_ids.length>1)){
 for(const id of award.recipient_ids){
  const attributed=app.awardsForRecipient(id).find(a=>a.award_id===award.award_id);
  assert.ok(attributed,'Historical recipient sees every award with an attributed action');
  const expected=app.state.data.transactions.filter(t=>t.award_id===award.award_id&&t.recipient_id===id).reduce((a,t)=>a+t.obligation,0);
  assert.ok(Math.abs(attributed.attributed_net_obligations-expected)<1e-8,'Recipient ledger uses action-time attribution');
 }
}
app.state.year='2024';app.state.selectedAward='unrelated-award';app.state.selectedRecipient='unrelated-recipient';
const caseDossier=app.dossier(app.state.cases[0]);
assert.equal(caseDossier.selection.fiscal_year,'all','Case scope ignores explorer fiscal-year filter');
assert.equal(caseDossier.source_records.length,4683,'Case preserves complete denominator and cited source history');
assert.ok(caseDossier.source_records.some(t=>t.award_id===app.state.cases[0].record.award_id));
for(const [id,choice] of [['a-b','merged'],['b-c','merged'],['a-c','separate']]){
 listeners.click({target:{closest:()=>({dataset:{scenarioId:id,scenario:choice},hasAttribute:()=>false})}});
 assert.equal(Object.keys(app.state.scenario).length,1,'Only one conditional identity preview is retained');
 assert.equal(app.state.scenario[id],choice);
}
if(app.state.data.meta.generation_id){
 app.state.year='2023';app.state.selectedAward=null;app.state.selectedRecipient=null;app.state.search='';app.state.scenario={};
 const preview=app.state.linkage.experiments.queue[0];app.state.scenario={[preview.id]:'separate'};
 const award=app.selectedAwards()[0];app.state.search=String(award.piid||award.award_id).slice(0,8);
 app.state.selectedAward=award.award_id;app.state.selectedRecipient=award.recipient_id;
 document.querySelector('#investigation-notes').value='Challenge: inspect the underlying modification.';
 const saved=app.investigation();assert.ok(saved.record_ids.length>0);assert.equal(saved.metrics.transactions,saved.record_ids.length);
 app.state.year='all';app.state.search='';app.state.selectedAward=null;app.state.selectedRecipient=null;
 app.state.search='x'.repeat(501);assert.throws(()=>app.investigation(),/longer than 500/);assert.equal(app.state.search.length,501);
 app.state.search='';app.openInvestigation(saved);assert.equal(app.state.year,'2023');assert.equal(app.state.search,saved.selection.search);assert.equal(app.state.scenario[preview.id],'separate');
 assert.deepEqual(JSON.parse(JSON.stringify(app.investigation())),JSON.parse(JSON.stringify(saved)));
 const reordered={...saved,metrics:Object.fromEntries(Object.entries({...saved.metrics,competition:Object.fromEntries(Object.entries(saved.metrics.competition).reverse())}).reverse())};app.openInvestigation(reordered);
 assert.throws(()=>app.openInvestigation({...saved,metrics:{...saved.metrics,extra:1}}));
 app.state.scenario={[preview.id]:'unresolved'};const unresolved=app.investigation();app.state.scenario={};app.openInvestigation(unresolved);assert.equal(app.state.scenario[preview.id],'unresolved');
 for(const altered of [{...saved,source:{...saved.source,generation_id:'wrong'}},{...saved,metrics:{...saved.metrics,net:saved.metrics.net+1}}]){
  assert.throws(()=>app.openInvestigation(altered));assert.equal(app.state.year,'2023');
 }
 if(process.argv.includes('--open-investigation')) {const reopened=JSON.parse(fs.readFileSync(process.argv[process.argv.indexOf('--open-investigation')+1]));app.openInvestigation(reopened);assert.deepEqual(JSON.parse(JSON.stringify(app.investigation())),reopened);}
 if(process.argv.includes('--export-investigation')) fs.writeFileSync(process.argv[process.argv.indexOf('--export-investigation')+1],JSON.stringify(saved,null,2));
}
if(process.argv.includes('--export-sql')){
 const i=process.argv.indexOf('--export-sql');
 fs.writeFileSync(process.argv[i+1],JSON.stringify(app.metricDefs,null,2));
}
console.log(JSON.stringify({status:'pass',transactions:all.transactions,net:all.net,negative:all.negative,competition:all.competition,all_window_hhi:all.hhi,annual_reconciliation:'FY2022–FY2024 net, HHI and top-four share match warehouse'},null,2));
