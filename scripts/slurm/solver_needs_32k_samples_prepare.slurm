#!/usr/bin/env bash
#SBATCH --job-name=solver-needs-32k-prepare
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
python -m unittest discover -s tests -p 'test_solver_needs*.py' -v
source_study="${1:?Completed 24k study}"
study_a="${2:?80x3 study}"
study_b="${3:?50x5 study}"
pool="${4:?Shared initial events}"
python -m solver_needs_study prepare --study "$study_a" --tasks 100 \
    --selection configs/solver-needs-tasks100.json \
    --config configs/solver-needs-qwen14b-internals32k-80x3.json \
    --reuse-initial-from "$source_study" --shared-initial-events "$pool"
python -m solver_needs_study prepare --study "$study_b" --tasks 100 \
    --selection configs/solver-needs-tasks100.json \
    --config configs/solver-needs-qwen14b-internals32k-50x5.json \
    --reuse-initial-from "$source_study" --shared-initial-events "$pool"
