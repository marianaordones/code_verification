#!/usr/bin/env bash
#SBATCH --job-name=z3-advanced-pilot
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=03:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit through scripts/submit_z3_advanced_pilot.sh}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_runtime.sh
source scripts/cluster/native_workspace.sh
native_workspace 2
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p test_z3_advanced_pilot.py -v
python -m diagnostics.z3_advanced_pilot run \
    --study "${1:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}" \
    --output "${2:-results/z3-advanced-pilot/job-${SLURM_JOB_ID}}" \
    --per-category 3 --repetitions 3 --timeout-ms 5000 --max-trace-mb 64
