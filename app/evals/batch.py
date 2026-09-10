"""Run a bounded funded evaluation batch inside one Slurm allocation."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.evals.budget import MAX_CLOUDBANK_EVALUATION_MICROUSD, PersistentSpendCap
from app.llm.catalog import load_model_catalog


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", action="append", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--phase", choices=("baseline", "tuning", "regression"), default="baseline")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    if not os.getenv("SLURM_JOB_ID"):
        parser.error("full evaluation batches must run in a Slurm allocation")
    if not 1 <= args.workers <= min(4, int(os.getenv("SLURM_CPUS_PER_TASK", "1"))):
        parser.error("workers must fit the allocated CPUs and cannot exceed four")
    catalog = load_model_catalog()
    for route_id in args.route:
        route = catalog.routes.get(route_id)
        if route is None or route.provider not in {"azure-foundry", "gcp-vertex"} or route.billing_source != "cloudbank":
            parser.error("batch routes must be configured CloudBank Azure/GCP routes")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = (args.output_dir or ROOT / "artifacts" / "evals" / f"{stamp}-{args.phase}").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Open the one shared ledger before launching workers. Its lifetime ceiling
    # includes all earlier smoke, baseline, tuning, and regression processes.
    budget = PersistentSpendCap(phase=args.phase)
    jobs = []

    def run_route(route_id):
        output = directory / f"{route_id}.json"
        command = [
            sys.executable, "-m", "app.evals.funded", "--route", route_id,
            "--repetitions", str(args.repetitions), "--phase", args.phase,
            "--paid-run-cap-microusd", str(MAX_CLOUDBANK_EVALUATION_MICROUSD),
            "--output", str(output), "--no-fail-on-gate",
        ]
        for case_id in args.case:
            command.extend(("--case", case_id))
        if output.with_suffix(".checkpoint.jsonl").exists():
            command.append("--resume")
        with (directory / f"{route_id}.log").open("a", encoding="utf-8") as log:
            # Fixed Python/module argv, validated catalog route, and no shell.
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)  # noqa: S603
        return {"route": route_id, "returncode": result.returncode, "report": str(output)}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        jobs = list(executor.map(run_route, list(dict.fromkeys(args.route))))
    receipt = {"jobs": jobs, "cloudbank_budget": budget.snapshot(), "directory": str(directory)}
    (directory / "batch.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all(job["returncode"] == 0 for job in jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
