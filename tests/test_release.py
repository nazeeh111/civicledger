"""Fail closed on mixed snapshots or incomplete public research artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def test_linkage_runtime_and_input_lineage_are_verified():
    manifest = read("data/processed/manifest.json")
    expected = {"snapshot_id": manifest["snapshot_id"], "public_csv_sha256": manifest["public_csv"]["sha256"]}
    payload = read("data/linkage/linkage.json")
    assert payload["source"] == expected
    for kind in ("real", "synthetic"):
        benchmark = payload["benchmark"][kind]
        assert benchmark["source"] == expected
        assert benchmark["splink_verification"]["status"] == "passed"
        assert benchmark["splink_verification"]["all_pairs"] == benchmark["split"]["test"]["pairs"]
    assert payload["summary"]["identifier_coverage"] == 1
    assert payload["queue"] == []  # Do not invent unresolved identities in this release.


def test_public_projection_has_the_same_evidence_as_source_artifacts():
    pairs = [("data/linkage/linkage.json", "linkage.json"), ("data/reports/cases.json", "cases.json"),
             ("data/reports/analysis.json", "reports.json"),
             ("data/processed/peer_award_year.json", "peer_award_year.json"),
             ("data/processed/revision_lag.json", "revision_lag.json")]
    for source, public in pairs:
        assert hashlib.sha256((ROOT / source).read_bytes()).digest() == hashlib.sha256((ROOT / "app/dist" / public).read_bytes()).digest(), public
    assert read("app/dist/data.json")["meta"]["public_csv_sha256"] == read("data/processed/manifest.json")["public_csv"]["sha256"]


def test_policy_comparisons_have_equal_review_budgets():
    payload = read("data/linkage/linkage.json")
    for experiment in (payload["experiments"], payload["synthetic_experiments"]):
        policies = {}
        for row in experiment["policies"]:
            policies.setdefault(row["policy"], set()).add((row["budget"], row["replicates"]))
        assert set(policies) == {"random", "uncertainty_only", "decision_sensitive"}
        assert len({tuple(sorted(v)) for v in policies.values()}) == 1
        for question in experiment["queue"]:
            assert question["component_id"]
            assert question["scope"] == "masked_identifier_experiment"
            assert question["decision"]["label"]
            assert question["merged"]["top_three"] and question["separate"]["top_three"]
