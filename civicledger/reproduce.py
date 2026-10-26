"""One entry point for an offline rebuild or an explicitly requested source refresh."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(args: list[str], env=None):
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Download a new USAspending snapshot; preserves old raw directories")
    parser.add_argument("--skip-linkage", action="store_true", help="Rebuild warehouse/reports only; retains existing linkage evidence")
    parser.add_argument("--replicates", type=int, default=20, help="Equal-budget review-policy experiment replicates")
    parser.add_argument("--test", action="store_true", help="Run the Python tests after regeneration")
    args = parser.parse_args()
    if args.refresh and args.skip_linkage:
        parser.error("--refresh requires rerunning linkage; do not combine it with --skip-linkage")
    if args.refresh:
        command([sys.executable, "-m", "civicledger.ingest"])
    manifest = json.loads((ROOT / "data/processed/manifest.json").read_text())
    actual = hashlib.sha256((ROOT / "data/processed/transactions.csv").read_bytes()).hexdigest()
    if actual != manifest["public_csv"]["sha256"]:
        raise RuntimeError("Published CSV differs from its retrieval manifest; refusing to build mixed evidence")
    command([sys.executable, "-m", "civicledger.warehouse"])
    env = os.environ.copy()
    env["CIVICLEDGER_DB"] = str(ROOT / "data/warehouse.duckdb")
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    dbt = str(Path(sys.executable).parent / "dbt")
    command([dbt, "build", "--project-dir", "dbt", "--profiles-dir", "dbt"], env=env)
    from civicledger.warehouse import export_dbt
    export_dbt()
    command([sys.executable, "-m", "civicledger.reports"])
    if not args.skip_linkage:
        command([sys.executable, "-m", "civicledger.linkage", "--replicates", str(args.replicates)])
    evidence = json.loads((ROOT / "data/linkage/linkage.json").read_text())
    expected_source = {"snapshot_id": manifest["snapshot_id"], "public_csv_sha256": actual}
    if evidence.get("source") != expected_source:
        raise RuntimeError("Linkage evidence does not match the input snapshot; rerun without --skip-linkage")
    for label in ("real", "synthetic"):
        if evidence["benchmark"][label]["splink_verification"]["status"] != "passed":
            raise RuntimeError(f"{label} Splink runtime verification has not passed")
    dist = ROOT / "app/dist"
    for source, target in [
        ("data/reports/cases.json", "cases.json"),
        ("data/reports/analysis.json", "reports.json"),
        ("data/linkage/linkage.json", "linkage.json"),
        ("data/processed/peer_award_year.json", "peer_award_year.json"),
        ("data/processed/revision_lag.json", "revision_lag.json"),
    ]:
        shutil.copyfile(ROOT / source, dist / target)
    command(["node", "app/check-data.mjs"])
    if args.test:
        command([sys.executable, "-m", "pytest", "-q"])
    print("Rebuild complete. Serve app/dist with python -m http.server --directory app/dist", flush=True)


if __name__ == "__main__":
    main()
