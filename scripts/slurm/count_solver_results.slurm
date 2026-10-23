#!/usr/bin/env bash
#SBATCH --job-name=verus-count-z3
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
# Read-only analysis of existing results: no GPU or ML runtime initialization.
run_directory="${1:-results/qwen25coder14b-b-150/seed-20261018/full/instruct}"
python3 scripts/count_solver_results.py "$run_directory" \
    --output "${run_directory}/solver-counts.json"
