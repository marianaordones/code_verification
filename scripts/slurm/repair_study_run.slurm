#!/usr/bin/env bash
#SBATCH --job-name=verus-repair-study
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
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$PROJECT_ROOT"
source scripts/cluster/job_init.sh
source scripts/cluster/stage_tools.sh
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p test_tools.py -v
python -m repair_study run --study "${1:?Study directory}" --mode "${2:?full or local}"
