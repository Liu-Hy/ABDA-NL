#!/bin/bash
#SBATCH --job-name=abda-prompt-eval
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/evals/slurm-%j.log

set -euo pipefail

# Submit from the repository and select the user's valid allocation with
# sbatch --account=... --partition=... evals/run_cloudbank.slurm --route ...
# One node keeps concurrent workers beside the same durable reservation ledger.
cd "${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
exec .venv/bin/python -m app.evals.batch "$@"
