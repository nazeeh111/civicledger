"""Cross-artifact checks for public findings and source-lineage exports."""
import csv
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_case_records_point_to_exact_source_rows():
    source = list(csv.DictReader((ROOT / "data/processed/transactions.csv").open()))
    cases = json.loads((ROOT / "data/reports/cases.json").read_text())
    assert len(cases) == 3
    assert len({c["id"] for c in cases}) == 3
    for case in cases:
        record = case["record"]
        matches = [x for x in source if x["contract_award_unique_key"] == record["award_id"]]
        assert matches
        assert record["url"] in {x["usaspending_permalink"] for x in matches}
        if "transaction_id" in record:
            match, = [x for x in matches if x["contract_transaction_unique_key"] == record["transaction_id"]]
            assert Decimal(str(record["obligation"])) == Decimal(match["federal_action_obligation"])
        assert case["alternative_explanations"] and case["uncertainty"]


def test_eda_and_canonical_warehouse_agree_on_concentration_and_totals():
    r = json.loads((ROOT / "data/reports/analysis.json").read_text())
    warehouse = json.loads((ROOT / "data/processed/analytics.json").read_text())
    for row in r["annual"]:
        canonical, = [x for x in warehouse["annual"] if x["fiscal_year"] == row["fy"]]
        assert abs(row["hhi"] - canonical["hhi"]) < 1e-8
        assert Decimal(str(row["net"])) == Decimal(str(canonical["net_obligations"]))
        assert abs(row["september_positive_share"] - canonical["september_share"]) < 1e-10


def test_signed_accounting_and_bootstrap_bounds():
    r = json.loads((ROOT / "data/reports/analysis.json").read_text())
    o = r["overview"]
    assert Decimal(str(o["net"])) == Decimal(str(o["positive"])) + Decimal(str(o["negative"]))
    assert o["positive_actions"] + o["negative_actions"] + o["zero_actions"] == o["transactions"]
    assert {x["fy"] for x in r["september_award_mix_bootstrap"]} == {2022, 2023, 2024}
    assert all(0 <= x["p025"] <= x["p975"] <= 1 for x in r["september_award_mix_bootstrap"])
