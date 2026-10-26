"""Identifier-masked linkage benchmarks and cluster-consistent decision experiments.

Run from the repository root: python -m civicledger.linkage [--csv data/processed/transactions.csv]
All monetary concentration metrics use positive net recipient exposure; signed
obligations remain in the warehouse and are reported separately. Scenario ranges
are sensitivity bounds within the candidate graph, never confidence intervals.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path
import re

import duckdb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_fscore_support
from scipy.special import expit, logit, logsumexp
from scipy.stats import kendalltau, beta

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "linkage"
SEED = 20261025
FEATURES = ("name", "city", "state")


def normalize_name(value: str | None) -> str:
    """Conservative lexical normalization; never establishes business identity."""
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def stable_split(entity: str) -> str:
    """Entity-disjoint split fixed before feature fitting or metric inspection."""
    u = int(sha256(("civicledger-holdout-v1:" + entity).encode()).hexdigest()[:12], 16) % 100
    return "train" if u < 60 else "calibration" if u < 80 else "test"


def all_partitions(items):
    """Yield every set partition exactly once (restricted-growth recursion)."""
    items = tuple(items)
    if not items:
        yield ()
        return
    head, *tail = items
    for p in all_partitions(tail):
        yield ((head,),) + p
        for j in range(len(p)):
            yield p[:j] + ((head,) + p[j],) + p[j+1:]


def membership(partition):
    return {item: group for group, block in enumerate(partition) for item in block}


def hhi_for_partition(partition, spend):
    amounts = [max(0.0, sum(float(spend[i]) for i in block)) for block in partition]
    exposure = sum(amounts)
    if exposure <= 0:
        return 0.0
    return 10000.0 * sum(v*v for v in amounts) / exposure**2


@dataclass
class Component:
    ids: tuple
    partitions: list
    weights: np.ndarray

    def condition(self, a, b, same):
        keep = np.array([(membership(p)[a] == membership(p)[b]) == same for p in self.partitions])
        if not keep.any():
            raise ValueError("Review answer contradicts every supported cluster partition")
        self.partitions = [p for p, k in zip(self.partitions, keep) if k]
        self.weights = self.weights[keep]
        self.weights /= self.weights.sum()


def make_component(ids, pair_prob):
    """A distribution over coherent partitions, not independent edge sampling.

    Weights are composite likelihoods of calibrated pair scores. They are not
    claimed to be calibrated cluster posterior probabilities.
    """
    ids = tuple(ids)
    if len(ids) > 7:
        raise ValueError("Exact partition enumeration supports blocks of at most seven records")
    partitions = list(all_partitions(ids))
    logweights = []
    for p in partitions:
        groups = membership(p)
        lw = 0.0
        for a, b in itertools.combinations(ids, 2):
            prob = float(np.clip(pair_prob.get(tuple(sorted((a,b))), 1e-5), 1e-5, 1-1e-5))
            lw += math.log(prob if groups[a] == groups[b] else 1-prob)
        logweights.append(lw)
    weights = np.exp(np.array(logweights) - logsumexp(logweights))
    return Component(ids, partitions, weights)


def worlds(components, singleton_ids, spend, n=512, seed=SEED):
    """Sample component partitions; every generated world is an equivalence relation."""
    rng = np.random.default_rng(seed)
    ids = sorted(spend)
    matrix = np.zeros((n, len(ids)), dtype=np.float64)
    hh = np.zeros(n)
    partitions = []
    draws = [rng.choice(len(c.partitions), size=n, p=c.weights) for c in components]
    for k in range(n):
        p = tuple((i,) for i in singleton_ids) + tuple(block for c,d in zip(components, draws) for block in c.partitions[d[k]])
        values = [(max(0.0,sum(float(spend[x]) for x in block)), tuple(sorted(block))) for block in p]
        values.sort(key=lambda x:(-x[0],x[1]))
        tops = {x for _,b in values[:3] for x in b}
        matrix[k] = [float(x in tops) for x in ids]
        total=sum(v for v,_ in values)
        hh[k] = 10000 * sum(v*v for v,_ in values) / total**2 if total>0 else 0.0
        partitions.append(p)
    # HHI scaled to unit interval; top-three-membership loss weight declared.
    decision_vectors = np.column_stack((hh / 10000.0, matrix * math.sqrt(0.1 / max(len(ids),1))))
    return hh, matrix, partitions, decision_vectors


def query_value(decision_vectors, answers):
    """Expected reduction in squared-error Bayes risk from one binary review."""
    answers = np.asarray(answers, dtype=bool)
    q = answers.mean()
    if q <= 0 or q >= 1:
        return 0.0
    difference = decision_vectors[answers].mean(axis=0) - decision_vectors[~answers].mean(axis=0)
    return float(q*(1-q)*np.dot(difference,difference))


def pair_answers(partitions, a, b):
    return np.array([membership(p)[a] == membership(p)[b] for p in partitions])


def ece(y, p, bins=10):
    y, p = np.asarray(y), np.asarray(p)
    result = 0.0
    table=[]
    for low in np.linspace(0,1,bins,endpoint=False):
        high=low+1/bins
        mask=(p>=low)&((p<high) if high<1-1e-9 else (p<=1))
        if mask.any():
            observed=float(y[mask].mean()); predicted=float(p[mask].mean())
            result += mask.mean()*abs(observed-predicted)
            table.append({"lower":round(float(low),2),"upper":round(float(high),2),"n":int(mask.sum()),"mean_probability":predicted,"observed_match_rate":observed})
    return float(result),table


def metrics(y, p, method, threshold=0.5):
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float); pred=p>=threshold
    precision,recall,f1,_=precision_recall_fscore_support(y,pred,average="binary",zero_division=0)
    fp=int(((y==0)&pred).sum()); fn=int(((y==1)&~pred).sum())
    cal,table=ece(y,p)
    tp=int(((y==1)&pred).sum())
    interval=lambda k,n: [float(beta.ppf(.025,k+.5,n-k+.5)),float(beta.ppf(.975,k+.5,n-k+.5))] if n else None
    return {"method":method,"threshold":threshold,"pairs":len(y),"positive_pairs":int(y.sum()),"precision":float(precision),"recall":float(recall),"precision_95_jeffreys_interval":interval(tp,tp+fp),"recall_95_jeffreys_interval":interval(tp,tp+fn),"interval_note":"Binomial pair-level intervals; overlapping pairs are dependent, so these are descriptive and can be optimistic.","f1":float(f1),"brier":float(brier_score_loss(y,p)),"ece":cal,"false_positives":fp,"false_negatives":fn,"error_cost":10*fp+fn,"cost_definition":"10 × false merges + missed links; illustrative review preference, not observed harm","average_precision":float(average_precision_score(y,p)) if y.sum() else None,"calibration_bins":table}


def pairs_for(records):
    """All pairs, including cross-block pairs, so blocking misses count in recall."""
    if len(records)<2:
        return pd.DataFrame()
    con=duckdb.connect()
    con.register("records",records)
    pairs=con.execute("""
      select l.record_id as left_id, r.record_id as right_id,
      cast(l.entity = r.entity as int) as label,
      cast(l.raw_name = r.raw_name as int) as exact,
      cast(l.name = r.name as int) as normalized,
      case when l.name=r.name then 0
           when jaro_winkler_similarity(l.name,r.name)>=0.95 then 1
           when jaro_winkler_similarity(l.name,r.name)>=0.85 then 2 else 3 end as name_level,
      case when l.city is null or r.city is null then -1 when l.city=r.city then 0 else 1 end as city_level,
      case when l.state is null or r.state is null then -1 when l.state=r.state then 0 else 1 end as state_level
      from records l join records r on l.record_id < r.record_id
      order by left_id,right_id
    """).df()
    con.close()
    return pairs


def train_fs(train_pairs):
    # Label-backed entity identity is used solely to estimate train m/u and prior.
    y=train_pairs.label.to_numpy()
    n=len(y)
    prior=float((y.sum()+0.5)/(n+1))
    parameters={}
    for feature,levels in (("name",4),("city",2),("state",2)):
        x=train_pairs[f"{feature}_level"].to_numpy()
        ms=np.array([((x[y==1]==k).sum()+0.5) for k in range(levels)])
        us=np.array([((x[y==0]==k).sum()+0.5) for k in range(levels)])
        parameters[feature]={"m":(ms/ms.sum()).tolist(),"u":(us/us.sum()).tolist()}
    return {"prior":prior,"parameters":parameters,"smoothing":0.5}


def fs_predict(pairs,model):
    odds=np.full(len(pairs),logit(model["prior"]))
    for feature in FEATURES:
        x=pairs[f"{feature}_level"].to_numpy()
        pp=model["parameters"][feature]
        valid=x>=0
        odds[valid] += np.log(np.array(pp["m"])[x[valid]] / np.array(pp["u"])[x[valid]])
    return expit(odds)


def splink_predict(records,model):
    """Splink inference with transparent train-only supervised m/u parameters."""
    from splink import Linker, SettingsCreator, DuckDBAPI
    import splink.comparison_library as cl
    comps=[]
    for feature in FEATURES:
        c=cl.JaroWinklerAtThresholds("name",[0.95,0.85]) if feature=="name" else cl.ExactMatch(feature)
        par=model["parameters"][feature]
        comps.append(c.configure(m_probabilities=par["m"],u_probabilities=par["u"]))
    settings=SettingsCreator(link_type="dedupe_only",comparisons=comps,blocking_rules_to_generate_predictions=["1=1"],probability_two_random_records_match=model["prior"],unique_id_column_name="record_id")
    # Entity label, UEI, DUNS, award IDs, dates, spending and split never enter linker.
    features=records[["record_id",*FEATURES]].copy()
    db_api=DuckDBAPI()
    frame=db_api.register(features,dataset_display_name="heldout_features")
    linker=Linker(frame,settings)
    prediction=linker.inference.predict(threshold_match_probability=0).as_pandas_dataframe()
    return {(min(int(r.record_id_l),int(r.record_id_r)),max(int(r.record_id_l),int(r.record_id_r))):float(r.match_probability) for r in prediction.itertuples()}


def calibrator_fit(p,y):
    # Isotonic is held out from both FS fitting and final test reporting.
    if len(np.unique(y))<2:
        return None
    # Jeffreys beta(0.5,0.5) smoothing per isotonic plateau prevents eight
    # observed matches from being presented as a 100%-certain identity claim.
    initial=IsotonicRegression(out_of_bounds="clip").fit(p,y)
    fitted=initial.predict(p)
    smoothed=np.zeros(len(y),dtype=float)
    for level in np.unique(fitted):
        mask=fitted==level
        smoothed[mask]=(np.asarray(y)[mask].sum()+0.5)/(mask.sum()+1)
    return IsotonicRegression(out_of_bounds="clip",y_min=0.00001,y_max=0.99999).fit(p,smoothed)


def candidate_components(records,pairs,p,cutoff=0.05):
    adjacency=defaultdict(set)
    pairprob={tuple(sorted((int(a),int(b)))):float(q) for a,b,q in zip(pairs.left_id,pairs.right_id,p)}
    for (a,b),q in pairprob.items():
        if q>=cutoff:
            adjacency[a].add(b);adjacency[b].add(a)
    components=[];singletons=[];excluded=[];visited=set()
    for i in records.record_id:
        i=int(i)
        if i in visited:continue
        todo=[i];block=[]
        while todo:
            k=todo.pop()
            if k in visited:continue
            visited.add(k);block.append(k);todo.extend(adjacency[k]-visited)
        block=tuple(sorted(block))
        if len(block)==1:singletons.extend(block)
        elif len(block)>7:
            # No arbitrary graph cut: keep unresolved identifiers separate and disclose.
            singletons.extend(block);excluded.append(block)
        else:components.append(make_component(block,pairprob))
    return components,singletons,excluded,pairprob


def truth_partition(records):
    return tuple(tuple(int(x) for x in g.record_id) for _,g in records.groupby("entity",sort=True))


def rank_agreement(partition,truth,spend):
    """Kendall rank association of each observation's grouped exposure."""
    def score(p):
        return {i:max(0.0,sum(float(spend[j]) for j in block)) for block in p for i in block}
    a,b=score(partition),score(truth)
    ids=sorted(spend)
    tau=kendalltau([a[x] for x in ids],[b[x] for x in ids]).statistic
    return float(tau) if np.isfinite(tau) else 1.0


def experiment(records,pairs,p,replicates=20,world_count=384,max_budget=10):
    """Equal-budget oracle review with entity IDs hidden except in review answers."""
    initial,singles,excluded,pairprob=candidate_components(records,pairs,p)
    spend={int(r.record_id):float(r.net_obligations) for r in records.itertuples()}
    truth=truth_partition(records);truth_hhi=hhi_for_partition(truth,spend)
    entity=dict(zip(records.record_id,records.entity))
    support_groups={i:ci for ci,c in enumerate(initial) for i in c.ids}
    support_groups.update({i:len(initial)+j for j,i in enumerate(singles)})
    positives=pairs[pairs.label==1]
    unsupported=sum(support_groups[int(a)]!=support_groups[int(b)] for a,b in zip(positives.left_id,positives.right_id))
    support_recall=1-unsupported/len(positives) if len(positives) else None
    possible=[(a,b) for c in initial for a,b in itertools.combinations(c.ids,2)]
    budget=min(max_budget,len(possible));budgets=sorted(set([0,1,3,5,budget]) & set(range(budget+1)))
    rows=[]
    for policy in ["random","uncertainty_only","decision_sensitive"]:
        for rep in range(replicates):
            rng=np.random.default_rng(SEED+rep)
            cs=[Component(c.ids,list(c.partitions),c.weights.copy()) for c in initial]
            asked=set()
            for step in range(budget+1):
                hh,top,ps,vec=worlds(cs,singles,spend,n=world_count,seed=SEED+rep*100+step)
                ordered_ids=sorted(spend);positions={i:j for j,i in enumerate(ordered_ids)}
                maps=[membership(partition) for partition in ps]
                labels=np.asarray([[m[i] for i in ordered_ids] for m in maps])
                if step in budgets:
                    # One coherent modal sampled world for ranking; posterior mean for HHI.
                    counts=Counter(ps)
                    modal=max(range(len(ps)),key=lambda k:counts[ps[k]])
                    rows.append({"policy":policy,"replicate":rep,"budget":step,"hhi_estimate":float(hh.mean()),"hhi_absolute_error":float(abs(hh.mean()-truth_hhi)),"hhi_scenario_width":float(np.quantile(hh,.975)-np.quantile(hh,.025)),"ranking_stability":rank_agreement(ps[modal],truth,spend),"top_three_membership_stability":float(1-4*np.var(top,axis=0).mean())})
                if step==budget:break
                candidates=[]
                for ci,c in enumerate(cs):
                    for a,b in itertools.combinations(c.ids,2):
                        if (a,b) in asked:continue
                        answer=labels[:,positions[a]]==labels[:,positions[b]];q=float(answer.mean())
                        if q<=0 or q>=1:continue
                        score= float(rng.random()) if policy=="random" else q*(1-q) if policy=="uncertainty_only" else query_value(vec,answer)
                        candidates.append((score,float(rng.random()),ci,a,b))
                if not candidates:
                    # Spend remaining equal budgets on zero-information known outcomes.
                    available=[(ci,a,b) for ci,c in enumerate(cs) for a,b in itertools.combinations(c.ids,2) if (a,b) not in asked]
                    if not available:break
                    ci,a,b=available[0]
                else:_,_,ci,a,b=max(candidates)
                asked.add((a,b));cs[ci].condition(a,b,entity[a]==entity[b])
    summary=[]
    for (policy,b),g in pd.DataFrame(rows).groupby(["policy","budget"]):
        obj={"policy":policy,"budget":int(b),"replicates":len(g)}
        for metric in ["hhi_absolute_error","hhi_scenario_width","ranking_stability","top_three_membership_stability"]:
            vals=g[metric].to_numpy()
            obj[metric]=float(vals.mean());obj[metric+"_sd"]=float(vals.std(ddof=1)) if len(vals)>1 else 0
        summary.append(obj)
    hh,top,ps,vec=worlds(initial,singles,spend,n=1024)
    ordered_ids=sorted(spend);positions={i:j for j,i in enumerate(ordered_ids)}
    maps=[membership(partition) for partition in ps]
    labels=np.asarray([[m[i] for i in ordered_ids] for m in maps])
    queue=build_review_queue(records,pairs,p)
    return {"source":records.attrs.get("source"),"scope":"Real observed records and amounts with identifiers deliberately masked; oracle answers use held-out identifiers. Not a live missing-ID population.","policies":summary,"raw_replicates":rows,"queue":queue[:20],"records":len(records),"candidate_components":len(initial),"excluded_oversized_components":[list(c) for c in excluded],"candidate_pair_count":len(possible),"unsupported_reference_links":unsupported,"reference_link_support_recall":support_recall,"reference_partition_supported":unsupported==0,"truth_hhi":truth_hhi,"hhi_before_review":float(hh.mean()),"hhi_range":[float(hh.min()),float(hh.max())],"replicates":replicates,"world_count":world_count,"seed":SEED,"loss":"Var(HHI/10000) + 0.1 × mean Var(top-three cluster membership by observed record). Expected reduction after an oracle pair answer. Weights fixed before evaluation.","limitations":["Identifier equality is a proxy for legal-entity identity, not adjudicated ownership or misconduct.","Repeated simulation seeds quantify Monte Carlo/review-order variation, not a population confidence interval.","Composite-likelihood scenario weights are not calibrated partition probabilities.","Candidate edges require calibrated score >= 0.05; disconnected and oversized components stay separate, so support misses can leave irreducible error.","Review queries are simulated oracle responses, not human adjudication; equal pair budgets do not measure equal human time."]}


def json_safe(value):
    if isinstance(value,(np.integer,)):return int(value)
    if isinstance(value,(np.floating,)):return float(value) if np.isfinite(value) else None
    if isinstance(value,Path):return str(value)
    raise TypeError(type(value).__name__)


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,default=json_safe,allow_nan=False)+"\n")



# Read only the public, privacy-reviewed snapshot.
def load_records(csv_path):
    csv_path=Path(csv_path)
    actual_hash=sha256(csv_path.read_bytes()).hexdigest()
    manifest_path=csv_path.parent/"manifest.json"
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    expected_hash=manifest.get("public_csv",{}).get("sha256")
    if expected_hash is not None and expected_hash != actual_hash:
        raise ValueError("Public CSV digest does not match its retrieval manifest")
    source={"snapshot_id":manifest.get("snapshot_id"),"public_csv_sha256":actual_hash}
    tx=pd.read_csv(csv_path,dtype=str,keep_default_na=False)
    tx["federal_action_obligation"]=pd.to_numeric(tx["federal_action_obligation"],errors="raise")
    keys=["recipient_uei","recipient_name","recipient_city_name","recipient_state_code"]
    records=tx.groupby(keys,sort=True,dropna=False).agg(net_obligations=("federal_action_obligation","sum"),transaction_count=("contract_transaction_unique_key","count"),award_url=("usaspending_permalink","first")).reset_index()
    records=records.rename(columns=dict(zip(keys,["entity","raw_name","city","state"])))
    records["name"]=records.raw_name.map(normalize_name)
    for c in ["city","state"]: records[c]=records[c].map(normalize_name).replace("",None)
    records["record_id"]=np.arange(len(records),dtype=int)
    records["split"]=records.entity.map(stable_split)
    records.attrs["source"]=source
    return tx,records


def perturb_records(records):
    """Visible stress test: artificial typographic/missingness variants only."""
    out=[]
    for row in records.to_dict("records"):
        for k in range(3):
            r=dict(row);r["net_obligations"]=float(row["net_obligations"])/3
            rng=np.random.default_rng(int(sha256(f"{row['record_id']}:{k}:perturb-v1".encode()).hexdigest()[:12],16))
            if k==1:r["raw_name"]=re.sub(r"\b(INCORPORATED|CORPORATION|COMPANY|LIMITED|LLC|INC|CORP|CO|LTD)\b","",normalize_name(row["raw_name"]))
            elif k==2:
                chars=list(normalize_name(row["raw_name"]))
                if len(chars)>5:
                    j=int(rng.integers(1,len(chars)-1));chars[j],chars[j+1]=chars[j+1],chars[j]
                    if len(chars)>15:chars.pop(int(rng.integers(1,len(chars)-1)))
                r["raw_name"]="".join(chars)
            r["name"]=normalize_name(r["raw_name"])
            if k and rng.random()<0.3:r["city"]=None
            if k and rng.random()<0.15:r["state"]=None
            out.append(r)
    df=pd.DataFrame(out);df["record_id"]=np.arange(len(df),dtype=int)
    df.attrs["source"]=records.attrs.get("source")
    return df


def run_benchmark(records,label,run_splink=True):
    groups={s:g.reset_index(drop=True) for s,g in records.groupby("split")}
    pairs={s:pairs_for(groups[s]) for s in ["train","calibration","test"]}
    if any(p.empty or p.label.sum()==0 for p in pairs.values()):
        raise ValueError("A three-way entity-disjoint benchmark needs positive pairs in every split")
    model=train_fs(pairs["train"])
    cal=calibrator_fit(fs_predict(pairs["calibration"],model),pairs["calibration"].label.to_numpy())
    raw=fs_predict(pairs["test"],model);p=cal.predict(raw) if cal else raw;y=pairs["test"].label.to_numpy()
    result={"source":records.attrs.get("source"),"status":"completed","scope":label,"features":list(FEATURES),"identifier_features":[],"split_method":"SHA256 entity hash, 60/20/20 buckets; no entity crosses splits","split":{s:{"records":len(groups[s]),"entities":int(groups[s].entity.nunique()),"pairs":len(pp),"positive_pairs":int(pp.label.sum())} for s,pp in pairs.items()},"methods":[metrics(y,pairs["test"].exact,"Exact raw name"),metrics(y,pairs["test"].normalized,"Normalized name"),metrics(y,raw,"Fellegi–Sunter / Splink"),metrics(y,p,"Held-out calibrated Fellegi–Sunter")],"model":model,"calibration":{"method":"Isotonic regression with Jeffreys beta(0.5,0.5) plateau smoothing on calibration entities only","x_thresholds":cal.X_thresholds_.tolist() if cal else [],"y_thresholds":cal.y_thresholds_.tolist() if cal else []},"limitations":["UEI equality is an identifier-backed proxy, not independent human-adjudicated identity.","Natural source records have one observed name per UEI; positive pairs chiefly test location changes, not misspellings.","Only name, city and state are compared. City/state correlation can overstate conditional-independence evidence.","All test pairs are evaluated without negative subsampling. Rare-match errors can hide behind low Brier/ECE; read precision/recall too.","Calibration is cohort-prevalence specific; probabilities do not transfer unchanged to a blocked or missing-ID population.","A 0.5 threshold and illustrative false-merge cost 10 were fixed without test optimization."]}
    if run_splink:
        try:
            predictions=splink_predict(groups["test"],model)
            check=np.array([predictions[(int(a),int(b))] for a,b in zip(pairs["test"].left_id,pairs["test"].right_id)])
            result["splink_verification"]={"status":"passed" if np.allclose(check,raw,atol=1e-9,rtol=1e-7) else "disagreed","version":__import__("splink").__version__,"all_pairs":len(check),"max_abs_probability_difference":float(np.max(abs(check-raw))),"role":"Splink runtime inference with train-only supervised m/u; independent transparent FS calculation checks likelihood ratios."}
        except Exception as exc:result["splink_verification"]={"status":"failed","error":str(exc)}
        if result["splink_verification"]["status"]!="passed":
            write_json(OUT/f"{label}_benchmark.json",result)
            raise RuntimeError("Splink baseline verification failed: " + str(result["splink_verification"]))
    pred=pairs["test"].copy();pred["raw_probability"]=raw;pred["calibrated_probability"]=p
    write_json(OUT/f"{label}_benchmark.json",result);pred.to_csv(OUT/f"{label}_test_pairs.csv",index=False)
    groups["test"][["record_id",*FEATURES,"net_obligations","award_url"]].to_csv(OUT/f"{label}_test_features.csv",index=False)
    groups["test"][["record_id","entity"]].to_csv(OUT/f"{label}_test_labels.csv",index=False)
    return result,groups["test"],pred,p


def run(csv_path,replicates=20):
    OUT.mkdir(parents=True,exist_ok=True);tx,records=load_records(csv_path)
    benchmark,test,pairs,p=run_benchmark(records,"real_observed")
    experiments=experiment(test,pairs,p,replicates=replicates)
    write_json(OUT/"real_review_experiment.json",experiments)
    print("real review experiment complete",flush=True)
    stress,st,sp,scores=run_benchmark(perturb_records(records),"synthetic_perturbation")
    print("synthetic benchmark complete",flush=True)
    stress_experiment=None
    if st is not None:
        entities=sorted(st.entity.unique(),key=lambda x:sha256(x.encode()).hexdigest())[:30]
        small=st[st.entity.isin(entities)].copy();pp=pairs_for(small);raw=fs_predict(pp,stress["model"])
        cx=stress["calibration"];cal=IsotonicRegression(out_of_bounds="clip").fit(cx["x_thresholds"],cx["y_thresholds"])
        stress_experiment=experiment(small,pp,cal.predict(raw),replicates=max(5,min(replicates,10)),world_count=256,max_budget=5)
    base=tx.groupby("recipient_uei").federal_action_obligation.sum();pos=base.clip(lower=0);hhi=float(10000*((pos/pos.sum())**2).sum())
    name_net=tx.groupby("recipient_name").federal_action_obligation.sum().clip(lower=0);name_hhi=float(10000*((name_net/name_net.sum())**2).sum())
    collisions=[]
    for name,g in tx.groupby("recipient_name"):
        ids=sorted(g.recipient_uei.unique())
        if len(ids)>1:collisions.append({"name":name,"distinct_identifiers":len(ids),"recipient_ueis":ids,"award_urls":list(dict.fromkeys(g.usaspending_permalink))[:4],"interpretation":"Same name, different UEIs. Keep legal recipients separate; parent grouping is a different question."})
    payload={"source":records.attrs.get("source"),"summary":{"status":"identifier_complete","scope":"NRC awarding-agency contract transactions, FY2022–FY2024","records":len(records),"entities":int(tx.recipient_uei.nunique()),"ambiguous_components":0,"identifier_coverage":float((tx.recipient_uei!="").mean()),"observed_hhi":hhi,"lower_hhi":hhi,"upper_hhi":hhi,"name_only_hhi":name_hhi,"interpretation":"Every transaction has a UEI. No probabilistic merge is needed in the released cohort. The masked-identifier experiment tests review behavior if identifiers were absent.","same_name_different_id":collisions,"positive_net_entity_exposure":float(pos.sum()),"signed_net_obligations":float(base.sum())},"queue":[],"benchmark":{"real":benchmark,"synthetic":stress},"experiments":experiments,"synthetic_experiments":stress_experiment,"method":{"formula":"HHI = 10000 × Σ(positive-net recipient obligations / Σ positive-net recipient obligations)^2. Partition weights ∝ product of pair match scores inside clusters and nonmatch scores across clusters.","sql":"SELECT recipient_id, SUM(obligation) AS net FROM fact_transactions GROUP BY recipient_id; -- positive net exposures for HHI, signed net retained separately","notes":["No fraud labels or fraud-detection accuracy.","Entity means UEI recipient, not beneficial owner or parent company.","Production identifiers remain intact; benchmark identifiers are hidden from features only.","Scenario ranges describe model support, not confidence intervals."],"sources":[{"title":"Splink documentation","url":"https://moj-analytical-services.github.io/splink/"},{"title":"Splink comparison configuration","url":"https://github.com/moj-analytical-services/splink/blob/master/splink/internals/comparison_creator.py"},{"title":"USAspending transaction API","url":"https://api.usaspending.gov/docs/endpoints"}]}}
    write_json(OUT/"linkage.json",payload);write_json(OUT/"real_review_experiment.json",experiments)
    if stress_experiment:write_json(OUT/"synthetic_review_experiment.json",stress_experiment)
    print(json.dumps({"records":len(records),"test":benchmark["split"]["test"],"methods":[{k:m[k] for k in ["method","precision","recall","brier","ece","error_cost"]} for m in benchmark["methods"]],"splink":benchmark.get("splink_verification"),"components":experiments["candidate_components"],"queue":len(experiments["queue"]),"hhi":hhi,"name_hhi":name_hhi},indent=2))


def build_review_queue(records,pairs,p):
    cs,singles,excluded,probs=candidate_components(records,pairs,p)
    spend={int(r.record_id):float(r.net_obligations) for r in records.itertuples()}
    hh,top,ps,vec=worlds(cs,singles,spend,n=1024)
    ids=sorted(spend);positions={i:j for j,i in enumerate(ids)}
    maps=[membership(partition) for partition in ps]
    labels=np.asarray([[m[i] for i in ids] for m in maps])
    names=dict(zip(records.record_id,records.raw_name));urls=dict(zip(records.record_id,records.award_url))
    def conditional(answer):
        selected=[partition for partition,keep in zip(ps,answer) if keep]
        counts=Counter(selected);modal=max(selected,key=lambda partition:counts[partition])
        ranked=[(max(0.0,sum(spend[i] for i in block)),tuple(sorted(block))) for block in modal]
        ranked.sort(key=lambda item:(-item[0],item[1]));den=sum(v for v,_ in ranked) or 1
        rows=[{"names":list(dict.fromkeys(names[i] for i in block)),"record_ids":list(block),"net_obligations":sum(spend[i] for i in block),"positive_net_exposure_share":v/den} for v,block in ranked[:3]]
        return {"hhi":float(hh[answer].mean()),"top_three":rows,"top_three_record_ids":sorted(i for row in rows for i in row["record_ids"]),"modal_partition_sample_support":counts[modal]/len(selected),"scenario_count":len(selected),"ranking_label":"Top three positive-net exposure clusters in the conditional modal sampled partition; other components remain unresolved."}
    queue=[]
    for ci,c in enumerate(cs):
        for a,b in itertools.combinations(c.ids,2):
            answers=labels[:,positions[a]]==labels[:,positions[b]];q=float(answers.mean())
            if q<=0 or q>=1:continue
            merged=conditional(answers);separate=conditional(~answers)
            survives=merged["top_three_record_ids"]==separate["top_three_record_ids"]
            queue.append({"id":f"masked-{a}-{b}","component_id":f"component-{ci}","names":[names[a],names[b]],"probability":probs[(a,b)],"partition_same_weight":q,"probability_label":"Held-out calibrated pair score; scenario weights are not calibrated cluster probabilities","decision_impact":query_value(vec,answers),"hhi_change":abs(merged["hhi"]-separate["hhi"]),"reason":"Review can change which three recipient exposure clusters are selected for contextual procurement review; high exposure is not evidence of wrongdoing.","evidence":[{"url":urls[a]},{"url":urls[b]}],"separate":separate,"merged":merged,"decision":{"label":"Which three positive-net exposure clusters receive contextual procurement review?","survives_pair_alternatives":survives,"interpretation":"The selected observations survive both conditional modal rankings." if survives else "The selected observations change between conditional modal rankings.","scenario_top_three_membership_stability":float(1-4*np.var(top,axis=0).mean()),"support_note":"Modal sampled partitions and scenario support, not confidence bounds or a claim of true identity."},"scope":"masked_identifier_experiment","review_status":"unreviewed","component_size":len(c.ids)})
    queue.sort(key=lambda row:-row["decision_impact"])
    return queue[:20]


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--csv",default=str(ROOT/"data/processed/transactions.csv"));parser.add_argument("--replicates",type=int,default=20);args=parser.parse_args();run(Path(args.csv),args.replicates)

if __name__=="__main__":main()
