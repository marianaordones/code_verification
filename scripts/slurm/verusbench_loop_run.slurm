#!/usr/bin/env bash
#SBATCH --job-name=verus-loop-false
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=1-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
source scripts/cluster/job_init.sh
source scripts/cluster/stage_tools.sh
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p test_loop_isolation.py -v
python -m baseline.verusbench_loop_isolation run --output "${1:?Output}" --batch "${2:?batch50 or batch55}"
