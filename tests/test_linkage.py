"""Behavioral tests for the uncertainty workflow and data/feature boundary."""
from pathlib import Path
import itertools
import math

import numpy as np
import pandas as pd
import pytest

from civicledger.linkage import (
    all_partitions, make_component, membership, worlds, hhi_for_partition,
    query_value, pair_answers, normalize_name, stable_split, load_records,
    calibrator_fit, train_fs, fs_predict, pairs_for,
)


def test_partition_enumeration_is_complete_and_unique():
    partitions=list(all_partitions([0,1,2,3]))
    assert len(partitions)==15  # Bell number B4
    canonical={tuple(sorted(tuple(sorted(b)) for b in p)) for p in partitions}
    assert len(canonical)==15
    for p in partitions:
        assert sorted(itertools.chain.from_iterable(p))==[0,1,2,3]


def test_partition_sampler_never_creates_incompatible_pairwise_matches():
    # Contradictory triangle of input edge scores must still produce valid clusters.
    c=make_component((0,1,2),{(0,1):.99,(1,2):.99,(0,2):.01})
    assert np.isclose(c.weights.sum(),1)
    _,_,ps,_=worlds([c],[],{0:10.,1:20.,2:30.},n=400,seed=42)
    for p in ps:
        m=membership(p)
        if m[0]==m[1] and m[1]==m[2]:assert m[0]==m[2]


def test_review_conditions_whole_partitions_and_propagates_transitivity():
    c=make_component((0,1,2),{(0,1):.5,(1,2):.5,(0,2):.5})
    c.condition(0,1,True)
    assert all(membership(p)[0]==membership(p)[1] for p in c.partitions)
    c.condition(1,2,True)
    assert len(c.partitions)==1
    assert membership(c.partitions[0])[0]==membership(c.partitions[0])[2]
    with pytest.raises(ValueError,match="contradicts"):
        c.condition(0,2,False)


def test_signed_obligations_are_summed_before_positive_exposure():
    # Clipping -80 before grouping would produce 5,000 instead of 7,222.22 HHI.
    spend={0:100,1:-80,2:100}
    p=((0,1),(2,))
    assert hhi_for_partition(p,spend)==pytest.approx(10000*(20**2+100**2)/120**2)
    c=make_component((0,1),{(0,1):.5});c.condition(0,1,True)
    hh,_,_,_=worlds([c],[2],spend,n=10)
    assert np.allclose(hh,hhi_for_partition(p,spend))


def test_decision_value_rewards_material_consequences_not_just_uncertainty():
    # Pair A has probability .5 but tiny effect, pair B .8 with large effect.
    a=np.array([0,0,1,1,0,0,1,1,0,0],dtype=bool)
    b=np.array([0,0,1,1,1,1,1,1,1,1],dtype=bool)
    decision=np.column_stack((.001*a + .5*b,))
    assert query_value(decision,b)>query_value(decision,a)
    assert query_value(decision,np.ones(10,dtype=bool))==0


def test_finite_calibration_support_does_not_claim_certainty():
    cal=calibrator_fit(np.array([.01]*30+[.9]*8),np.array([0]*30+[1]*8))
    assert 0 < cal.predict([0])[0] < .5
    assert .5 < cal.predict([1])[0] < 1


def test_identifier_never_appears_in_comparison_features():
    records=pd.DataFrame([
        {"record_id":0,"entity":"UEI_A","name":"ALPHA","raw_name":"ALPHA","city":"A","state":"VA"},
        {"record_id":1,"entity":"UEI_A","name":"ALPHA","raw_name":"ALPHA","city":"B","state":"VA"},
        {"record_id":2,"entity":"UEI_B","name":"BETA","raw_name":"BETA","city":"C","state":"VA"},
    ])
    pairs=pairs_for(records);model=train_fs(pairs)
    renamed=records.copy();renamed["entity"]=["Z","Z","Q"]
    assert np.allclose(fs_predict(pairs,model),fs_predict(pairs_for(renamed),model))
    assert set(model["parameters"])=={"name","city","state"}


def test_real_record_adapter_reconciles_money_and_keeps_entity_splits_disjoint():
    path=Path(__file__).parents[1]/"data/processed/transactions.csv"
    if not path.exists():pytest.skip("public data snapshot not installed")
    tx,r=load_records(path)
    assert r.net_obligations.sum()==pytest.approx(tx.federal_action_obligation.sum(),abs=.01)
    assert len(tx)==tx.contract_transaction_unique_key.nunique()
    assert (tx.recipient_uei!="").all()
    assert r.groupby("entity").split.nunique().max()==1
    assert (r.net_obligations<0).any()
    sets={s:set(g.entity) for s,g in r.groupby("split")}
    assert not (sets["train"]&sets["test"] or sets["calibration"]&sets["test"] or sets["train"]&sets["calibration"])


def test_review_queue_exports_conditional_named_rankings_and_survival():
    from civicledger.linkage import build_review_queue
    r=pd.DataFrame([
        {"record_id":0,"entity":"A","raw_name":"ALPHA","name":"ALPHA","city":"X","state":"VA","net_obligations":50.,"award_url":"https://example.test/0"},
        {"record_id":1,"entity":"A","raw_name":"ALPHA","name":"ALPHA","city":"Y","state":"VA","net_obligations":50.,"award_url":"https://example.test/1"},
        {"record_id":2,"entity":"B","raw_name":"BETA","name":"BETA","city":"Z","state":"VA","net_obligations":70.,"award_url":"https://example.test/2"},
        {"record_id":3,"entity":"C","raw_name":"GAMMA","name":"GAMMA","city":"Z","state":"VA","net_obligations":60.,"award_url":"https://example.test/3"},
    ])
    pairs=pairs_for(r);p=np.where((pairs.left_id==0)&(pairs.right_id==1),.5,.001)
    queue=build_review_queue(r,pairs,p)
    assert len(queue)==1
    row=queue[0]
    assert row["component_id"]=="component-0"
    assert row["merged"]["top_three"][0]["names"]==["ALPHA"]
    assert row["separate"]["top_three"][0]["names"]==["BETA"]
    assert row["decision"]["survives_pair_alternatives"] is False


def test_adapter_rejects_snapshot_digest_mismatch(tmp_path):
    import json
    csv=tmp_path/"transactions.csv";csv.write_text("unexpected,data\n1,2\n")
    (tmp_path/"manifest.json").write_text(json.dumps({"snapshot_id":"fixture","public_csv":{"sha256":"wrong"}}))
    with pytest.raises(ValueError,match="digest does not match"):
        load_records(csv)
