#!/usr/bin/env bash
#SBATCH --job-name=solver-needs-prepare
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_runtime.sh
python -m solver_needs_study.download data
source scripts/cluster/stage_solver_needs.sh
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p test_solver_needs_study.py -v
python -m solver_needs_study prepare --study "${1:?Study directory}" --tasks "${2:-100}" \
    --selection "${3:-configs/solver-needs-tasks100.json}"
