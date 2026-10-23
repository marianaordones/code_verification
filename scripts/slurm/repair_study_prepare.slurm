#!/usr/bin/env bash
#SBATCH --job-name=verus-repair-prepare
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_runtime.sh
source scripts/cluster/stage_tools.sh
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p test_repair_study.py -v
python -m repair_study prepare --source-run "${1:?Source run}" --study "${2:?Study directory}" --count "${3:-30}"
